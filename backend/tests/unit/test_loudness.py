import shutil
import subprocess

import numpy as np
import pytest

from src.detect.chat_spikes import detect_spikes
from src.media.loudness import loud_moments, loudness_per_second, rolling_median
from src.twitch_chat import chat_signal_lines

from tests.unit.test_chat_spikes import synthetic_chat


def quiet_db(seconds=900):
    rng = np.random.default_rng(1)
    return -40 + rng.normal(0, 0.8, seconds)


def test_a_loud_stretch_is_found_and_a_steady_stream_is_not():
    db = quiet_db()
    assert loud_moments(db) == []
    db[500:506] += 22
    moments = loud_moments(db)
    assert len(moments) == 1
    assert 499 <= moments[0]["peak_t"] <= 507
    assert moments[0]["win_start"] < moments[0]["peak_t"] < moments[0]["win_end"]


def test_the_baseline_follows_the_stream_level():
    db = np.concatenate([np.full(600, -50.0), np.full(600, -20.0)])
    assert abs(rolling_median(db)[100] + 50) < 1
    assert abs(rolling_median(db)[1100] + 20) < 1


def test_loud_moment_lines_use_the_prompt_format():
    db = quiet_db()
    db[500:506] += 22
    line = chat_signal_lines(loud_moments(db))
    assert line.startswith("- [") and "the audio got much louder" in line


def test_chat_plus_a_reaction_from_the_stream_is_still_a_spike():
    db = quiet_db()
    db[500:520] += 20
    assert detect_spikes(synthetic_chat(), audio_db=db)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_loudness_per_second_reads_a_real_file(tmp_path):
    clip = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=4", "-ac", "1", str(clip)], check=True)
    levels = loudness_per_second(clip)
    assert 3 <= len(levels) <= 5
    assert -30 < float(levels[1]) < 0
