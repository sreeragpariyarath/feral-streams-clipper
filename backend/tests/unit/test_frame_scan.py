import numpy as np

from src.media.frame_scan import _rank01, frame_scan_enabled, shortlist
from src.twitch_chat import chat_signal_lines


def rows():
    return [
        {"t": 10.0, "score": 0.9, "kind": "action", "look": "a car chase", "sound": []},       # inside the opening minute
        {"t": 120.0, "score": 0.8, "kind": "action", "look": "a car crash", "sound": ["Smash, crash"]},
        {"t": 130.0, "score": 0.7, "kind": "action", "look": "a car flipping", "sound": []},  # too close to 120
        {"t": 300.0, "score": 0.95, "kind": "boring", "look": "a loading screen", "sound": []},  # dull
        {"t": 400.0, "score": 0.6, "kind": "action", "look": "an explosion", "sound": []},
    ]


def test_shortlist_skips_the_opening_dull_frames_and_near_neighbours():
    picked = shortlist(rows(), count=5, gap=45, warmup=60)
    assert [r["t"] for r in picked] == [120.0, 400.0]


def test_shortlist_is_in_time_order_and_capped():
    assert [r["t"] for r in shortlist(rows(), count=1, warmup=0)] == [10.0]


def test_rank_normalises_any_scale():
    assert list(_rank01([5.0, 1.0, 3.0])) == [1.0, 0.0, 0.5]
    assert len(_rank01([])) == 0


def test_scan_is_off_by_default(monkeypatch):
    monkeypatch.delenv("FRAME_SCAN", raising=False)
    assert frame_scan_enabled() is False


def test_scan_moments_become_prompt_lines():
    line = chat_signal_lines([{"peak_t": 125, "win_start": 95, "win_end": 150, "h_score": 0.8,
                               "what": "a car crash, with Smash, crash on the audio", "signals": {}, "chat_top": {}, "chat_samples": []}])
    assert line.startswith("- [01:35 - 02:30]") and "on screen and in the audio: a car crash" in line
