from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

from localvideoai.audio.chunker import AudioChunk, iter_pcm_chunks
from localvideoai.core.exceptions import MediaError
from localvideoai.engines.audio_engine import AudioEngine
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


class FFmpegAudioEngine(AudioEngine):
    """Extract or stream audio via bundled FFmpeg. Long files are not slurped into Python."""

    @property
    def engine_id(self) -> str:
        return "ffmpeg-audio"

    @property
    def display_name(self) -> str:
        return "FFmpeg Audio Engine"

    def extract(self, media_path: Path, destination: Path) -> Path:
        source = media_path.expanduser().resolve()
        dest = destination.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                str(find_ffmpeg()),
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(dest),
            ],
            source,
        )
        if not dest.is_file() or dest.stat().st_size <= 0:
            raise MediaError(f"抽取音频失败：{dest}")
        return dest

    def resample(self, audio_path: Path, destination: Path, sample_rate: int) -> Path:
        if sample_rate <= 0:
            raise MediaError("采样率必须大于 0")
        source = audio_path.expanduser().resolve()
        dest = destination.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                str(find_ffmpeg()),
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                str(dest),
            ],
            source,
        )
        return dest

    def iter_chunks(self, media_path: Path, duration_ms: int, chunk_ms: int = 30_000, overlap_ms: int = 800) -> Iterator[AudioChunk]:
        return iter_pcm_chunks(media_path, duration_ms, chunk_ms=chunk_ms, overlap_ms=overlap_ms)

    def _run(self, command: list[str], source: Path) -> None:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            raise MediaError(f"FFmpeg 音频处理失败：{source}\n{(completed.stderr or '')[-2000:]}")
