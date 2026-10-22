"""Extract a short PCM window from local media without decoding the whole file."""

from __future__ import annotations

import subprocess
from pathlib import Path

from localvideoai.audio.chunker import CHANNELS, SAMPLE_RATE, AudioChunk
from localvideoai.core.exceptions import MediaError
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


def extract_pcm_window(
    media_path: Path,
    start_ms: int,
    end_ms: int,
    *,
    accurate_seek: bool = False,
) -> AudioChunk:
    source = media_path.expanduser().resolve()
    if not source.is_file():
        raise MediaError(f"媒体不存在：{source}")
    start = max(0, int(start_ms))
    end = max(start + 50, int(end_ms))
    duration_ms = end - start
    start_sec = f"{start / 1000:.3f}"
    duration_sec = f"{duration_ms / 1000:.3f}"
    command = [
        str(find_ffmpeg()),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
    ]
    if not accurate_seek:
        command.extend(["-ss", start_sec])
    command.extend(["-i", str(source)])
    if accurate_seek:
        command.extend(["-ss", start_sec])
    command.extend(
        [
            "-t",
            duration_sec,
            "-vn",
            "-sn",
            "-ac",
            str(CHANNELS),
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "pipe:1",
        ]
    )
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace")[-1500:]
        raise MediaError(f"无法抽取实时音频窗口：{source}\n{stderr}")
    payload = completed.stdout or b""
    return AudioChunk(index=0, start_ms=start, end_ms=end, pcm_s16le=payload)
