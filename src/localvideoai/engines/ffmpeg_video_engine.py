from __future__ import annotations

import subprocess
from pathlib import Path

from localvideoai.core.exceptions import MediaError
from localvideoai.core.types import VideoProbeResult
from localvideoai.engines.video_engine import VideoEngine
from localvideoai.media.ffmpeg_runtime import find_ffmpeg
from localvideoai.media.media_analyzer import MediaAnalyzer


class FFmpegVideoEngine(VideoEngine):
    """Local FFmpeg engine. Probe uses MediaAnalyzer and does not load the whole file."""

    def __init__(self) -> None:
        self._analyzer = MediaAnalyzer()

    @property
    def engine_id(self) -> str:
        return "ffmpeg"

    @property
    def display_name(self) -> str:
        return "FFmpeg Video Engine"

    def probe(self, path: Path) -> VideoProbeResult:
        return self._analyzer.analyze(path).to_probe_result()

    def extract_audio(self, path: Path, destination: Path) -> Path:
        source = path.expanduser().resolve()
        dest = destination.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(find_ffmpeg()),
            "-y",
            "-i",
            str(source),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(dest),
        ]
        self._run(command, source)
        if not dest.is_file():
            raise MediaError(f"抽取音频失败：{dest}")
        return dest

    def extract_frames(self, path: Path, destination_dir: Path, fps: float) -> list[Path]:
        if fps <= 0:
            raise MediaError("fps 必须大于 0")
        source = path.expanduser().resolve()
        folder = destination_dir.expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        pattern = folder / "frame_%06d.png"
        command = [
            str(find_ffmpeg()),
            "-y",
            "-i",
            str(source),
            "-vf",
            f"fps={fps}",
            str(pattern),
        ]
        self._run(command, source)
        frames = sorted(folder.glob("frame_*.png"))
        if not frames:
            raise MediaError(f"没有抽出帧：{source}")
        return frames

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
            raise MediaError(f"FFmpeg 失败：{source}\n{(completed.stderr or '')[-2000:]}")
