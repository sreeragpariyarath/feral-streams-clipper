import shutil
import subprocess

import pytest
from PIL import Image

from src.media import hook_card


def test_card_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("HOOK_CARD", raising=False)
    assert hook_card.hook_card_enabled() is False
    assert hook_card.apply_hook_card(tmp_path / "missing.mp4", "A title") is False


def test_card_png_is_transparent_with_a_red_border_and_wraps_long_titles(tmp_path):
    short = tmp_path / "short.png"
    long = tmp_path / "long.png"
    hook_card.render_hook_card("Easter egg", short)
    hook_card.render_hook_card("Ending the stream if there is no easter egg at all today", long)
    with Image.open(short) as card:
        assert card.mode == "RGBA"
        assert card.getchannel("A").getpixel((0, 0)) == 0  # the tilted corner is transparent
    with Image.open(long) as tall, Image.open(short) as flat:
        assert tall.size[1] > flat.size[1]


def test_emoji_only_title_is_refused(tmp_path):
    with pytest.raises(ValueError):
        hook_card.render_hook_card("\U0001F525\U0001F525", tmp_path / "x.png")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_card_keeps_the_clip_length_and_size(monkeypatch, tmp_path):
    monkeypatch.setenv("HOOK_CARD", "on")
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=360x640:d=3:r=30", "-pix_fmt", "yuv420p", str(clip)], check=True)
    assert hook_card.apply_hook_card(clip, "A big moment", 0.3) is True
    assert hook_card.ffprobe_video_size(clip) == (360, 640)
    assert abs(hook_card.ffprobe_duration(clip) - 3.0) < 0.2
