"""Frame scan: find clippable moments from what is on screen and what is heard, with local models.

Ported from the GTA clipper. ffmpeg grabs a small frame every few seconds (keyframes only, so a long VOD is
quick), CLIP rates each frame (action, a dull menu, something unsafe, something new) and PANNs listens for
sirens, gunfire, crashes, screaming and laughter. The best moments come back as hint lines for clip selection,
next to the chat and loudness hints. Nothing is sent to an API.

``FRAME_SCAN=on`` enables it (default off) and needs the ``frame-scan`` dependencies and the model weights
(``python -m src.media.local_models``); without them it quietly does nothing.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)

FRAME_W, FRAME_H = 384, 216


def frame_scan_enabled() -> bool:
    return (os.environ.get("FRAME_SCAN") or "off").strip().lower() in {"on", "1", "true", "yes"}


def grab_frames(video: Path, out_dir: Path, every: float = 8.0, *, timeout: int = 1800):
    """One small frame every ``every`` seconds (keyframes only). Returns (paths, real times in seconds)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info", "-skip_frame", "nokey", "-i", str(video),
        "-vf",
        f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{every - 0.5})',showinfo,"
        f"scale={FRAME_W}:{FRAME_H}:force_original_aspect_ratio=decrease,"
        f"pad={FRAME_W}:{FRAME_H}:(ow-iw)/2:(oh-ih)/2",
        "-fps_mode", "vfr", "-q:v", "5", str(out_dir / "f_%05d.jpg"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg frame extraction failed: " + " | ".join(result.stderr.splitlines()[-3:]))
    frames = sorted(out_dir.glob("f_*.jpg"))
    times = [float(x) for x in re.findall(r"pts_time:\s*([0-9.]+)", result.stderr)][: len(frames)]
    if len(times) < len(frames):
        times = [i * every for i in range(len(frames))]
    return frames, times


def _rank01(values: List[float]) -> np.ndarray:
    """Rank-normalise to 0..1, robust to each model's own scale."""
    array = np.asarray(values, dtype=float)
    return array.argsort().argsort() / max(1, len(array) - 1) if len(array) else array


def score_frames(frames: List[Path], times: List[float], video: Path) -> List[Dict[str, Any]]:
    """Per-frame scores from CLIP (look) and PANNs (sound). Raises when the models are unavailable."""
    from . import local_models as lm

    clip = lm.Clip()
    embeddings = clip.embed([str(f) for f in frames])
    looks = clip.score(embeddings)
    newness = lm.novelty(embeddings, times)

    tags: List[Dict[str, Any]] = []
    try:
        tags = lm.AudioTagger().tag_file(video)
    except Exception as exc:  # pictures alone are still useful
        logger.warning("Frame scan: audio model skipped (%s)", type(exc).__name__)

    action = _rank01([look["action"] - look["boring"] for look in looks])
    fresh = _rank01(list(newness))
    rows: List[Dict[str, Any]] = []
    for index, (t, look) in enumerate(zip(times, looks)):
        sound = lm.sound_at(tags, t) if tags else {"score": 0.0, "top": {}}
        score = 0.5 * action[index] + 0.25 * fresh[index] + 0.25 * min(1.0, sound["score"] * 1.5)
        if look["best_kind"] == "unsafe" or look["unsafe"] > 0.35:
            score *= 0.2
        if look["best_kind"] == "boring" and look["boring"] > 0.6:
            score *= 0.5
        rows.append({
            "t": float(t), "score": float(score), "look": look["best"], "kind": look["best_kind"],
            "sound": list(sound["top"].keys())[:3],
        })
    return rows


def shortlist(rows: List[Dict[str, Any]], count: int = 10, gap: float = 45.0, warmup: float = 60.0) -> List[Dict[str, Any]]:
    """The best moments, spaced apart, skipping dull and unsafe ones and the opening minute."""
    chosen: List[Dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: -r["score"]):
        if row["kind"] != "action" or row["t"] < warmup:
            continue
        if all(abs(row["t"] - other["t"]) >= gap for other in chosen):
            chosen.append(row)
        if len(chosen) >= count:
            break
    return sorted(chosen, key=lambda r: r["t"])


def scan_moments(video: Path, *, every: float = 8.0, count: int = 10) -> List[Dict[str, Any]]:
    """Candidate moments shaped like the chat-spike candidates, with a ``what`` description of the picture."""
    with tempfile.TemporaryDirectory(prefix="frame-scan-") as scratch:
        frames, times = grab_frames(video, Path(scratch), every)
        if not frames:
            return []
        rows = score_frames(frames, times, video)
    moments = []
    for index, row in enumerate(shortlist(rows, count), 1):
        what = row["look"] + (f", with {', '.join(row['sound'])} on the audio" if row["sound"] else "")
        moments.append({
            "id": index, "peak_t": int(row["t"]),
            "win_start": max(0, int(row["t"]) - 30), "win_end": int(row["t"]) + 25,
            "h_score": round(row["score"], 3), "what": what,
            "signals": {}, "chat_top": {}, "chat_samples": [],
        })
    return moments
