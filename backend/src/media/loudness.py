"""Loudness per second of a video's audio, and the moments that are much louder than the rest.

Ported from the GTA clipper. A streamer shouting, a crowd, an explosion: those seconds are far above
the stream's usual level. Measured relative to a rolling median, so a loud stream is not all "peaks".
Used two ways: fused with chat reactions (a spike needs chat *and* a reaction from the streamer), and
on its own as hints for videos with no chat.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


RATE = 8000  # loudness only: 8 kHz mono is plenty


def loudness_hints_enabled() -> bool:
    """Loud-moment hints for videos with no chat replay (``LOUDNESS_HINTS``, default off)."""
    return (os.environ.get("LOUDNESS_HINTS") or "off").strip().lower() in {"on", "1", "true", "yes"}


def loudness_per_second(video_path: Path, *, timeout: int = 1800) -> np.ndarray:
    """RMS level in dBFS for every second of the first audio track. Streams the file, so a long
    recording never sits in memory. Empty when there is no audio."""
    process = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video_path), "-vn",
         "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    levels: List[np.ndarray] = []
    chunk = RATE * 2 * 60  # a minute of int16 samples
    rest = b""
    try:
        while True:
            data = process.stdout.read(chunk)
            if not data:
                break
            data = rest + data
            usable = len(data) - len(data) % (RATE * 2)
            rest = data[usable:]
            if not usable:
                continue
            samples = np.frombuffer(data[:usable], dtype=np.int16).astype(np.float32).reshape(-1, RATE)
            rms = np.sqrt(np.mean(samples * samples, axis=1)) + 1e-6
            levels.append(20 * np.log10(rms / 32768))
    finally:
        process.stdout.close()
        process.wait(timeout=timeout)
    return np.concatenate(levels) if levels else np.zeros(0, dtype=np.float32)


def rolling_median(values: np.ndarray, window: int = 600, step: int = 10) -> np.ndarray:
    """A slow-moving baseline: the median of the surrounding ``window`` seconds."""
    count = len(values)
    if count == 0:
        return values.astype(np.float64)
    centers = list(range(0, count, step))
    medians = [np.median(values[max(0, c - window // 2):min(count, c + window // 2) + 1]) for c in centers]
    return np.interp(np.arange(count), centers, medians)


def loud_moments(
    db: np.ndarray,
    *,
    threshold: float = 0.35,
    warmup: int = 180,
    min_gap: int = 60,
    max_moments: int = 12,
    pre: int = 30,
    post: int = 25,
) -> List[Dict[str, Any]]:
    """Seconds far louder than the stream's usual level, strongest first, as candidate dicts
    (``peak_t``, ``win_start``, ``win_end``, ``h_score``) shaped like the chat-spike candidates."""
    count = len(db)
    if count < 300:
        return []
    excess = db - rolling_median(db)
    smooth = np.convolve(excess, np.ones(3) / 3, mode="same")  # a moment is a few loud seconds, not a click
    score = np.clip((smooth - 6) / 24, 0, 1)
    picked: List[int] = []
    for second in np.argsort(-score):
        if score[second] < threshold or len(picked) >= max_moments:
            break
        if second < warmup or any(abs(int(second) - p) < min_gap for p in picked):
            continue
        picked.append(int(second))
    picked.sort()
    return [
        {
            "id": index,
            "peak_t": peak,
            "win_start": max(0, peak - pre),
            "win_end": min(count, peak + post),
            "h_score": round(float(score[peak]), 3),
            "signals": {"loud_excess_db": round(float(smooth[peak]), 1), "m30": "n/a"},
            "chat_top": {},
            "chat_samples": [],
        }
        for index, peak in enumerate(picked, 1)
    ]
