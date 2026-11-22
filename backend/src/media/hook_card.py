"""Hook card: the clip's title on a tilted white card with a thick red border.

A bolder alternative to the burned-in hook title, drawn as a transparent PNG and laid over the clip with
ffmpeg for the opening seconds, usually on the seam between the facecam and the gameplay panel.

``HOOK_CARD=on`` turns it on (default ``off``: clips are untouched). It replaces the subtitle-style hook
title on clips that go through the plain render; clips drawn by the dynamic-edits renderer keep their own.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .common import HOOK_TITLE_MIN_SECONDS, hook_title_window
from .ffmpeg import build_final_video_encode_args, ffprobe_duration, ffprobe_video_size, run_ffmpeg_command

logger = logging.getLogger(__name__)

HOOK_CARD_ENV = "HOOK_CARD"

RED = (226, 51, 38, 255)
WHITE = (255, 255, 255, 255)
BLACK = (10, 10, 10, 255)

FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"
FONT_CANDIDATES = ("Anton-Regular.ttf", "BebasNeue-Regular.ttf", "ArchivoBlack-Regular.ttf", "Inter.ttf")

# Emoji and symbols cannot be drawn by these fonts.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D]")

# Where the card goes when the layout does not name a seam (fraction of the frame height).
DEFAULT_CENTER_Y = 0.27
CARD_WIDTH_FRACTION = 0.89
FADE_SECONDS = 0.2


def hook_card_enabled() -> bool:
    return (os.environ.get(HOOK_CARD_ENV) or "off").strip().lower() in {"on", "1", "true", "yes"}


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(str(FONTS_DIR / name), size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: float) -> List[str]:
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _fit(draw: ImageDraw.ImageDraw, text: str, max_width: float, start: int, lines_max: int, min_size: int):
    size = start
    while True:
        font = _font(size)
        lines = _wrap(draw, text, font, max_width)
        if len(lines) <= lines_max or size <= min_size:
            return font, lines, size
        size -= 4


def _tilt(image: Image.Image, degrees: float = 3, shear: float = 0.16) -> Image.Image:
    """An italic slant and a small counter-clockwise tilt. Works at double size for smooth edges."""
    image = image.resize((image.size[0] * 2, image.size[1] * 2), Image.LANCZOS)
    margin = int(image.size[1] * shear) + 20
    padded = Image.new("RGBA", (image.size[0] + 2 * margin, image.size[1] + 2 * margin), (0, 0, 0, 0))
    padded.paste(image, (margin, margin))
    height = padded.size[1]
    padded = padded.transform(padded.size, Image.AFFINE, (1, shear, -shear * height / 2, 0, 1, 0), resample=Image.BICUBIC)
    padded = padded.rotate(degrees, resample=Image.BICUBIC, expand=True)
    return padded.resize((padded.size[0] // 2, padded.size[1] // 2), Image.LANCZOS)


def render_hook_card(text: str, out_png: Path, *, frame_width: int = 1080) -> Tuple[int, int]:
    """Draw the card for ``text`` into ``out_png`` (transparent PNG). Returns its (width, height)."""
    text = _EMOJI.sub("", text or "").strip().upper()
    if not text:
        raise ValueError("hook card needs text")
    width = round(frame_width * CARD_WIDTH_FRACTION)
    border, pad_x, pad_y = 10, 34, 18
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    if len(text.split()) <= 4:
        font, lines, size = _fit(probe, text, width - 2 * (pad_x + border) - 20, 92, 1, 56)   # one big line
    else:
        font, lines, size = _fit(probe, text, min(width - 2 * (pad_x + border), 800), 80, 2, 44)
    line_height = int(size * 1.08)
    height = pad_y * 2 + line_height * len(lines) + 2 * border
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=30, fill=RED)
    draw.rounded_rectangle((border, border, width - 1 - border, height - 1 - border), radius=22, fill=WHITE)
    for index, line in enumerate(lines):
        line_width = draw.textlength(line, font=font)
        draw.text(((width - line_width) / 2, border + pad_y + index * line_height), line, font=font, fill=BLACK)
    card = _tilt(card)
    card.save(out_png)
    return card.size


def apply_hook_card(video_path: Path, title: str, center_y: Optional[float] = None) -> bool:
    """Lay the hook card over a rendered clip's opening seconds, in place. Returns whether the file changed.

    ``center_y`` is where the card's middle goes as a fraction of the frame height (the gaming layout
    passes its seam); without it the card sits near the top. A no-op unless ``HOOK_CARD=on``.
    """
    if not hook_card_enabled() or not (title or "").strip():
        return False
    frame_width, frame_height = ffprobe_video_size(video_path)
    duration = float(ffprobe_duration(video_path) or 0.0)
    window = hook_title_window(duration) if duration else HOOK_TITLE_MIN_SECONDS
    fraction = DEFAULT_CENTER_Y if center_y is None else min(max(float(center_y), 0.05), 0.9)
    with tempfile.TemporaryDirectory(prefix="hook-card-") as scratch:
        card_png = Path(scratch) / "card.png"
        card_width, card_height = render_hook_card(title, card_png, frame_width=frame_width)
        x = (frame_width - card_width) // 2
        y = max(0, round(frame_height * fraction - card_height / 2))
        out_path = Path(scratch) / f"out{video_path.suffix}"
        graph = (
            f"[1:v]format=rgba,fade=t=in:st=0.12:d={FADE_SECONDS}:alpha=1,"
            f"fade=t=out:st={max(0.2, window - FADE_SECONDS):.3f}:d={FADE_SECONDS}:alpha=1[card];"
            f"[0:v][card]overlay={x}:{y}:enable='between(t,0.12,{window:.3f})':format=auto,setsar=1[v]"
        )
        command = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_path),
            "-loop", "1", "-t", f"{duration if duration > 0 else window + 0.5:.3f}", "-i", str(card_png),
            "-filter_complex", graph,
            "-map", "[v]", "-map", "0:a?",
            *build_final_video_encode_args(),
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ]
        result = run_ffmpeg_command(command)
        if result.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"Unable to add the hook card to {video_path}: {result.stderr[-500:]}")
        shutil.move(str(out_path), str(video_path))
    return True

