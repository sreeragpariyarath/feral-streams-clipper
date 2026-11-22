import subprocess
from pathlib import Path

import pytest

from src.media import ffmpeg


def test_overlay_is_off_without_a_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CAMPAIGN_OVERLAY_FILE", raising=False)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")
    assert ffmpeg.campaign_overlay_settings() is None
    assert ffmpeg.apply_campaign_overlay(clip) is False
    assert clip.read_bytes() == b"clip"


def test_overlay_settings_read_the_environment(monkeypatch, tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"png")
    monkeypatch.setenv("CAMPAIGN_OVERLAY_FILE", str(logo))
    monkeypatch.setenv("CAMPAIGN_OVERLAY_WIDTH", "0.5")
    monkeypatch.setenv("CAMPAIGN_OVERLAY_Y", "0.02")
    assert ffmpeg.campaign_overlay_settings() == {"path": logo, "width": 0.5, "top": 0.02}
    monkeypatch.setenv("CAMPAIGN_OVERLAY_FILE", str(tmp_path / "missing.png"))
    assert ffmpeg.campaign_overlay_settings() is None


def test_overlay_burns_into_a_real_clip(monkeypatch, tmp_path):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    clip = tmp_path / "clip.mp4"
    logo = tmp_path / "logo.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=360x640:d=1", "-pix_fmt", "yuv420p", str(clip)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=200x80", "-frames:v", "1", str(logo)], check=True)
    monkeypatch.setenv("CAMPAIGN_OVERLAY_FILE", str(logo))
    assert ffmpeg.apply_campaign_overlay(clip) is True
    assert ffmpeg.ffprobe_video_size(clip) == (360, 640)
