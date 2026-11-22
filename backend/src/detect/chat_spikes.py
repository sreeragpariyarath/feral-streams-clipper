"""Chat spike detector (ported from the GTA clipper).

Feed chat messages with feed(), call tick(now) about once a second.
tick() returns finished candidates (dicts) once their post-roll has passed.
``detect_spikes`` runs the whole thing over a finished chat replay.

Score per second:
  s_chat   = 0.4 * burst(5s) + 0.6 * sustained(30s)    (robust z-scores vs rolling median/MAD)
  s_unique = unique chatters in 30s vs baseline
  s_emote  = hype tokens (LUL, KEKW, Pog, ????, CLIP IT ...) relative to volume
  H = 0.55*s_chat + 0.225*s_unique + 0.225*s_emote
Phase 0 has no audio / viewer-clip signals; their weight is spread over chat.
"""
import math
import statistics
from collections import Counter, defaultdict, deque

import re

DEFAULT_DETECT = {
    "threshold": 0.45, "min_m30": 15, "min_ratio": 1.6, "audio_threshold": 0.35,
    "pre_s": 45, "post_s": 20, "merge_s": 45, "cooldown_s": 30, "warmup_s": 180, "baseline_s": 600,
}

# whole-word reaction words (regex), plus emoji (substring)
WORDS = {
    "funny": r"lol+|lmao+|lmfao+|kekw|lul|omegalul|icant|i can'?t|ha(ha)+|dead+|crying|xd",
    "hype": r"pog\w*|lets? go+|let'?s go+|no way+|insane|goated|clean|cinema|peak",
    "shock": r"wtf|omg+|bruh+|nah+h*|yoo+|what the|holy|no shot|he crashed|slow down|bro what|wait what|\?{3,}",
    "clip": r"clip (it|that)|clipped|clip+",
}
EMOJI = {
    "funny": ["😂", "💀", "🤣", "😭"],
    "hype": ["🔥", "😤"],
    "shock": ["😱", "😳", "🤯"],
    "clip": [],
}
_WORD_RE = {k: re.compile(r"(?<![a-z])(" + v + r")(?![a-z])", re.I) for k, v in WORDS.items()}
CLASS_WEIGHT = {"funny": 1, "hype": 1, "shock": 1, "clip": 2}

# chat that has nothing to do with gameplay: giveaway begging, mod/sub requests, greetings
SPAM = re.compile(
    r"(?<![a-z])(ps5|ps 5|xbox|giveaway|give ?away|gift(ed)? me|gift a sub|buy me|pick me|choose me|"
    r"me please|me pls|can i (get|have|win)|i want (one|it|a)|how (do|to) (we|i|you) (win|enter)|"
    r"mod me|vip me|sub me|follow me|code|copy ?pasta|good ?morning|good ?night|hi+ kai|hello|"
    r"first time here|from (india|africa|nigeria|uk|canada))(?![a-z])", re.I)


def classify(msg):
    hits = []
    for cls, rx in _WORD_RE.items():
        if rx.search(msg) or any(e in msg for e in EMOJI[cls]):
            hits.append(cls)
    return hits


def norm(msg):
    """Normalize for duplicate/copypasta detection."""
    return re.sub(r"\s+", " ", re.sub(r"(.)\1{2,}", r"\1\1", msg.lower())).strip()[:60]


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def robust_z(value, history, floor_median=0.0):
    if len(history) < 30:
        return 0.0
    med = max(statistics.median(history), floor_median)
    mad = statistics.median(abs(h - med) for h in history)
    mad = max(mad, 1.0)
    return (value - med) / (1.4826 * mad)


class Detector:
    def __init__(self, cfg=None):
        d = {**DEFAULT_DETECT, **((cfg or {}).get("detect") or {})}
        self.thr = d["threshold"]
        self.min_m30 = d["min_m30"]
        self.pre = d["pre_s"]
        self.post = d["post_s"]
        self.merge = d["merge_s"]
        self.cooldown = d["cooldown_s"]
        self.warmup = d["warmup_s"]
        self.baseline_len = d["baseline_s"]
        self.min_ratio = d.get("min_ratio", 1.6)

        self.msgs = defaultdict(int)
        self.spam = defaultdict(int)          # filtered messages per second (for logs)
        self.recent_text = deque()            # (sec, normalized text) for copypasta collapse
        self.text_count = Counter()
        self.audio = {}                       # sec -> dB (live: from recorded segments)
        self.hist_db = deque(maxlen=600)
        self.audio_thr = d.get("audio_threshold", 0.35)
        self.audio_strong = d.get("audio_strong", 0.5)
        self.recent_audio = deque(maxlen=d.get("chat_lag_s", 20))   # chat reacts 5-20 s after the streamer
        self.users = defaultdict(set)
        self.emo = defaultdict(Counter)
        self.samples = defaultdict(list)

        self.hist_m5 = deque(maxlen=self.baseline_len)
        self.hist_m30 = deque(maxlen=self.baseline_len)
        self.hist_u30 = deque(maxlen=self.baseline_len)

        self.first_sec = None
        self.last_scored = None
        self.above = 0
        self.burst = None          # open burst {start, peak_t, peak_h, signals}
        self.pending = []          # closed bursts waiting for post-roll
        self.last_closed_end = -math.inf
        self.count = 0
        self.timeline = {}         # sec -> H (kept for summaries)

    # ---- input -------------------------------------------------------
    def feed(self, t, user, msg):
        if msg.startswith("!"):
            return
        sec = int(t)
        if self.first_sec is None:
            self.first_sec = sec
            self.last_scored = sec - 1
        if SPAM.search(msg):
            self.spam[sec] += 1
            return
        if user in self.users[sec]:            # one message per chatter per second
            return
        key = norm(msg)
        while self.recent_text and self.recent_text[0][0] < sec - 10:
            old = self.recent_text.popleft()[1]
            self.text_count[old] -= 1
        self.recent_text.append((sec, key))
        self.text_count[key] += 1
        # the same text repeated by many people (copypasta / spam waves) counts at most 3 times,
        # unless it is a short reaction ("LMAO", "W", "💀") - those ARE the signal
        if self.text_count[key] > 3 and not classify(msg):
            return
        self.msgs[sec] += 1
        self.users[sec].add(user)
        for cls in classify(msg):
            self.emo[sec][cls] += 1
        if len(self.samples[sec]) < 6:
            self.samples[sec].append(msg[:120])

    def feed_audio(self, sec, db):
        """Loudness (dB) of the stream for one wall-clock second."""
        self.audio[int(sec)] = float(db)

    def _audio_score(self, sec):
        """0..1: how much louder than usual the stream is around sec (3 s average). None = unknown."""
        vals = [self.audio[s] for s in (sec - 1, sec, sec + 1) if s in self.audio]
        if not vals:
            return None, None
        db = sum(vals) / len(vals)
        if sec in self.audio:
            self.hist_db.append(self.audio[sec])
        if len(self.hist_db) < 60:
            return 0.0, 0.0
        excess = db - statistics.median(self.hist_db)
        return clamp((excess - 5) / 15), round(excess, 1)

    # ---- scoring -----------------------------------------------------
    def _window(self, sec, n):
        m = sum(self.msgs.get(s, 0) for s in range(sec - n + 1, sec + 1))
        return m

    def _score(self, sec):
        m5 = self._window(sec, 5)
        m30 = self._window(sec, 30)
        users = set()
        emo = Counter()
        for s in range(sec - 29, sec + 1):
            users |= self.users.get(s, set())
            emo.update(self.emo.get(s, {}))
        u30 = len(users)
        emo30 = sum(CLASS_WEIGHT[c] * n for c, n in emo.items())

        base_m30 = statistics.median(self.hist_m30) if len(self.hist_m30) >= 30 else m30
        ratio = m30 / max(base_m30, 5)
        s_burst = clamp(robust_z(m5, self.hist_m5) / 6)
        s_sustain = clamp(robust_z(m30, self.hist_m30, floor_median=5) / 4)
        s_chat = 0.4 * s_burst + 0.6 * s_sustain
        s_unique = clamp(robust_z(u30, self.hist_u30) / 4)
        s_emote = clamp(emo30 / max(8, 0.5 * m30))
        h_chat = 0.55 * s_chat + 0.225 * s_unique + 0.225 * s_emote
        s_now, excess_db = self._audio_score(sec)
        if s_now is not None:
            self.recent_audio.append(s_now)
        if s_now is None and not self.recent_audio:   # no audio signal at all (VOD chat replay)
            s_audio = None
            h = h_chat
        else:
            s_audio = max(self.recent_audio) if self.recent_audio else 0.0  # streamer's reaction just before chat
            h = 0.65 * h_chat + 0.35 * s_audio

        self.hist_m5.append(m5)
        self.hist_m30.append(m30)
        self.hist_u30.append(u30)
        signals = {
            "m5": m5, "m30": m30, "u30": u30, "emo30": dict(emo),
            "s_chat": round(s_chat, 3), "s_unique": round(s_unique, 3),
            "s_emote": round(s_emote, 3), "ratio": round(ratio, 2),
            "h_chat": round(h_chat, 3), "s_audio": None if s_audio is None else round(s_audio, 3),
            "s_audio_now": None if s_now is None else round(s_now, 3),
            "loud_excess_db": excess_db, "spam5": sum(self.spam.get(x, 0) for x in range(sec - 4, sec + 1)),
        }
        return h, m30, ratio, signals

    def tick(self, now):
        """Score every whole second up to now-1. Returns ready candidates."""
        if self.first_sec is None:
            return []
        upto = int(now) - 1
        while self.last_scored < upto:
            sec = self.last_scored + 1
            self.last_scored = sec
            h, m30, ratio, signals = self._score(sec)
            self.timeline[sec] = round(h, 3)
            if sec - self.first_sec < self.warmup:
                continue
            chat_ok = m30 >= self.min_m30 and ratio >= self.min_ratio
            sa = signals["s_audio"]
            hc = signals["h_chat"]
            if sa is None:                                   # chat only
                hot = chat_ok and h >= self.thr
            else:
                hot = ((chat_ok and hc >= self.thr and sa >= 0.15)       # chat AND streamer react
                       or (chat_ok and hc >= self.thr + 0.3)              # chat goes crazy
                       or ((signals["s_audio_now"] or 0) >= self.audio_strong and ratio >= 0.9))  # streamer yells
            self.above = self.above + 1 if hot else 0
            if self.above >= 2 and self.burst is None and sec - self.last_closed_end >= self.cooldown:
                self.burst = {"start": sec - 1, "peak_t": sec, "peak_h": h, "signals": signals}
            if self.burst is not None:
                if h > self.burst["peak_h"]:
                    self.burst.update(peak_t=sec, peak_h=h, signals=signals)
                if not hot and sec - self.burst["peak_t"] > 3:
                    self._close(sec)
        ready = [c for c in self.pending if now >= c["win_end"] + 12]
        self.pending = [c for c in self.pending if c not in ready]
        return ready

    def _close(self, sec):
        b = self.burst
        self.burst = None
        self.last_closed_end = sec
        # merge with previous pending candidate if peaks are close
        if self.pending and b["peak_t"] - self.pending[-1]["peak_t"] <= self.merge:
            prev = self.pending[-1]
            if b["peak_h"] > prev["h_score"]:
                prev.update(self._make(b, prev["id"]))
            return
        self.count += 1
        self.pending.append(self._make(b, self.count))

    def _make(self, b, cid):
        t1 = b["peak_t"]
        top = Counter()
        samples = []
        for s in range(t1 - 15, t1 + 6):
            top.update(self.emo.get(s, {}))
            samples.extend(self.samples.get(s, []))
        return {
            "id": cid,
            "peak_t": t1,
            "win_start": t1 - self.pre,
            "win_end": t1 + self.post,
            "h_score": round(b["peak_h"], 3),
            "signals": b["signals"],
            "chat_top": dict(top.most_common(5)),
            "chat_samples": samples[-12:],
        }

    def flush(self):
        """End of stream / VOD: close any open burst and return everything pending."""
        if self.burst is not None:
            self._close(self.last_scored)
        out, self.pending = self.pending, []
        return out


def detect_spikes(messages, cfg=None, *, step=1):
    """Chat reaction peaks in a finished replay.

    ``messages`` is an iterable of ``(offset_seconds, user, text)`` sorted by offset (video time, not
    wall clock). Returns the candidate dicts, strongest first, each with ``peak_t`` (seconds into the
    video where chat peaked), ``h_score`` (0..1), ``chat_top`` and ``chat_samples``.
    """
    det = Detector(cfg)
    out = []
    last = 0
    for t, user, text in messages:
        t = float(t)
        # the replay's clock is the message clock: score every second that has fully passed
        while last + step <= int(t):
            last += step
            out.extend(det.tick(last))
        det.feed(t, str(user or ""), str(text or ""))
    out.extend(det.tick(last + 40))   # let the final post-roll expire
    out.extend(det.flush())
    # a candidate can be returned by tick and flush only once: dedupe by id
    seen, unique = set(), []
    for c in out:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        unique.append(c)
    return sorted(unique, key=lambda c: c["h_score"], reverse=True)
