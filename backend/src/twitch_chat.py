"""Chat replay of a Twitch VOD and the moments where chat reacted.

The replay is downloaded with TwitchDownloaderCLI (an open-source tool, installed in the backend
image); no Twitch account or token is needed. Everything here is best-effort: a VOD without chat,
a missing tool or a failed download just means the AI picks moments without chat hints.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .detect.chat_spikes import detect_spikes
from .media.transcription import format_ms_to_timestamp

logger = logging.getLogger(__name__)

# A multi-hour VOD has hundreds of thousands of messages; give the download room but not forever.
DOWNLOAD_TIMEOUT_SECONDS = 900
_VOD_ID = re.compile(r"twitch\.tv/(?:[^/]+/)?videos?/(\d+)", re.I)


def chat_spikes_enabled() -> bool:
    return (os.environ.get("CHAT_SPIKES") or "on").strip().lower() not in {"off", "0", "false", "no"}


def downloader_binary() -> Optional[str]:
    """The TwitchDownloaderCLI to run: ``TWITCH_DOWNLOADER_CLI`` or the one on PATH."""
    return shutil.which(os.environ.get("TWITCH_DOWNLOADER_CLI") or "TwitchDownloaderCLI")


def twitch_vod_id(url: str) -> Optional[str]:
    match = _VOD_ID.search(url or "")
    return match.group(1) if match else None


def parse_chat_json(payload: Any) -> List[Tuple[float, str, str]]:
    """TwitchDownloader's chat JSON -> ``(offset_seconds, user, text)`` sorted by video time."""
    comments = payload.get("comments") if isinstance(payload, dict) else None
    messages: List[Tuple[float, str, str]] = []
    for comment in comments or []:
        if not isinstance(comment, dict):
            continue
        text = str((comment.get("message") or {}).get("body") or "").strip()
        if not text:
            continue
        commenter = comment.get("commenter") or {}
        user = str(commenter.get("display_name") or commenter.get("name") or "")
        try:
            offset = float(comment.get("content_offset_seconds") or 0)
        except (TypeError, ValueError):
            continue
        messages.append((offset, user.lower(), text))
    messages.sort(key=lambda item: item[0])
    return messages


def download_vod_chat(video_id: str) -> List[Tuple[float, str, str]]:
    """Download a VOD's chat with TwitchDownloaderCLI. Blocking; raises when it cannot."""
    binary = downloader_binary()
    if binary is None:
        raise RuntimeError("TwitchDownloaderCLI is not installed")
    with tempfile.TemporaryDirectory(prefix="twitch-chat-") as scratch:
        output = Path(scratch) / "chat.json"
        result = subprocess.run(
            [binary, "chatdownload", "--id", video_id, "-o", str(output)],
            capture_output=True,
            text=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            env={**os.environ, "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1"},
        )
        if result.returncode != 0 or not output.exists():
            raise RuntimeError((result.stderr or result.stdout or "download failed").strip()[-300:])
        return parse_chat_json(json.loads(output.read_text(encoding="utf-8")))


def chat_signal_lines(spikes: Iterable[Dict[str, Any]], *, limit: int = 10) -> str:
    """Spikes as the signal lines the clip-selection prompt already understands."""
    lines: List[str] = []
    for spike in sorted(spikes, key=lambda item: item["h_score"], reverse=True)[:limit]:
        peak = int(spike["peak_t"])
        start = max(0, int(spike["win_start"]))
        end = max(start + 1, int(spike["win_end"]))
        signals = spike.get("signals") or {}
        score = min(10.0, 4.0 + 6.0 * float(spike["h_score"]))
        when = f"- [{format_ms_to_timestamp(start * 1000)} - {format_ms_to_timestamp(end * 1000)}] score={score:.1f}: "
        if spike.get("what"):
            lines.append(f"{when}on screen and in the audio: {spike['what']} (around {format_ms_to_timestamp(peak * 1000)})")
        elif spike.get("chat_top") or spike.get("chat_samples"):
            reaction = ", ".join(spike.get("chat_top") or {}) or "reactions"
            said = " | ".join((spike.get("chat_samples") or [])[-3:])
            loud = signals.get("loud_excess_db")
            louder = f", the stream got {loud} dB louder" if isinstance(loud, (int, float)) and loud > 3 else ""
            lines.append(
                f"{when}live chat reacted here (peak at {format_ms_to_timestamp(peak * 1000)}, "
                f"{signals.get('m30', '?')} messages in 30s, {reaction}{louder}); chat said: {said}"
            )
        else:
            lines.append(
                f"{when}the audio got much louder here (peak at {format_ms_to_timestamp(peak * 1000)}, "
                f"{signals.get('loud_excess_db', '?')} dB above the usual level)"
            )
    return "\n".join(lines)


def _loudness(video_path: Optional[Path]):
    """The video's loudness per second, or None when it cannot be measured."""
    if video_path is None:
        return None
    try:
        from .media.loudness import loudness_per_second

        levels = loudness_per_second(Path(video_path))
        return levels if len(levels) else None
    except Exception as exc:
        logger.warning("Loudness unavailable for %s: %s", video_path, exc)
        return None


def vod_chat_hints(url: str, video_path: Optional[Path] = None) -> Optional[str]:
    """Signal lines for a Twitch VOD URL, or None when it has no usable chat. Blocking.

    With ``video_path`` (the downloaded VOD) the streamer's loudness is fused in: a spike then needs chat
    and a reaction from the stream. The VOD must be the whole broadcast so chat offsets line up.
    """
    video_id = twitch_vod_id(url)
    if not video_id or not chat_spikes_enabled():
        return None
    try:
        messages = download_vod_chat(video_id)
        spikes = detect_spikes(messages, audio_db=_loudness(video_path))
    except Exception as exc:  # no tool, no chat, network: carry on without chat hints
        logger.warning("Twitch chat replay unavailable for VOD %s: %s", video_id, exc)
        return None
    if not spikes:
        logger.info("No chat spikes found in VOD %s", video_id)
        return None
    logger.info("Found %d chat spikes in VOD %s", len(spikes), video_id)
    return chat_signal_lines(spikes)


def loud_hints(video_path: Path) -> Optional[str]:
    """Signal lines for the loudest moments of any video (``LOUDNESS_HINTS=on``). Blocking."""
    from .media.loudness import loud_moments, loudness_hints_enabled

    if not loudness_hints_enabled():
        return None
    levels = _loudness(video_path)
    if levels is None:
        return None
    moments = loud_moments(levels)
    return chat_signal_lines(moments) if moments else None


def scan_hints(video_path: Path) -> Optional[str]:
    """Signal lines for the best-looking and best-sounding moments (``FRAME_SCAN=on``). Blocking."""
    from .media.frame_scan import frame_scan_enabled, scan_moments
    from .media.local_models import models_ready

    if not frame_scan_enabled():
        return None
    if not models_ready():
        logger.warning("FRAME_SCAN is on but the frame-scan libraries or model weights are missing")
        return None
    try:
        moments = scan_moments(Path(video_path))
    except Exception as exc:
        logger.warning("Frame scan failed for %s: %s", video_path, exc)
        return None
    return chat_signal_lines(moments) if moments else None
