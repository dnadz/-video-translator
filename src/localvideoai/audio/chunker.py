"""Stream audio from media with FFmpeg. Only one chunk sits in RAM at a time."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from localvideoai.core.exceptions import MediaError
from localvideoai.media.ffmpeg_runtime import find_ffmpeg

SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2


@dataclass(frozen=True)
class AudioChunk:
    index: int
    start_ms: int
    end_ms: int
    pcm_s16le: bytes
    sample_rate: int = SAMPLE_RATE
    channels: int = CHANNELS

    @property
    def sample_count(self) -> int:
        return len(self.pcm_s16le) // (BYTES_PER_SAMPLE * self.channels)


def iter_pcm_chunks(
    media_path: Path,
    duration_ms: int,
    chunk_ms: int = 30_000,
    overlap_ms: int = 800,
) -> Iterator[AudioChunk]:
    """Decode audio once as a stream. Yield 16 kHz mono PCM chunks; never slurp the file."""
    source = media_path.expanduser().resolve()
    if not source.is_file():
        raise MediaError(f"媒体不存在：{source}")
    if duration_ms <= 0:
        raise MediaError(f"无法按分段读取音频：时长无效：{source}")
    if chunk_ms <= 0:
        raise MediaError("分段时长必须大于 0")
    overlap_ms = max(0, min(overlap_ms, chunk_ms // 2))
    bytes_per_ms = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE / 1000
    chunk_bytes = max(1, int(chunk_ms * bytes_per_ms))
    overlap_bytes = int(overlap_ms * bytes_per_ms)
    command = [
        str(find_ffmpeg()),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(source),
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
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise MediaError(f"无法启动 FFmpeg 分段读取：{source}") from exc
    if process.stdout is None:
        process.kill()
        raise MediaError(f"FFmpeg 没有提供音频输出：{source}")
    leftover = b""
    emitted = 0
    start_ms = 0
    try:
        while True:
            need = chunk_bytes - len(leftover)
            incoming = _read_exact(process.stdout, need)
            payload = leftover + incoming
            if not payload:
                break
            actual_ms = int(len(payload) / bytes_per_ms)
            end_ms = start_ms + actual_ms
            yield AudioChunk(
                index=emitted,
                start_ms=start_ms,
                end_ms=min(end_ms, duration_ms) if duration_ms else end_ms,
                pcm_s16le=payload,
            )
            emitted += 1
            if len(payload) < chunk_bytes:
                break
            leftover = payload[-overlap_bytes:] if overlap_bytes else b""
            start_ms = end_ms - overlap_ms
        return_code = process.wait(timeout=120)
        if emitted == 0:
            raise MediaError(f"没有读到音频数据：{source}（FFmpeg 退出码 {return_code}）")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def _read_exact(stream, size: int) -> bytes:
    if size <= 0:
        return b""
    chunks = bytearray()
    remaining = size
    while remaining > 0:
        piece = stream.read(remaining)
        if not piece:
            break
        chunks.extend(piece)
        remaining -= len(piece)
    return bytes(chunks)
