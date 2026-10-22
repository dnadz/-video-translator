"""Probe exported files and classify player compatibility. No fake checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess

from localvideoai.core.exceptions import ExportError
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


@dataclass
class CompatReport:
    path: Path
    container: str
    video_codec: str
    audio_codec: str
    subtitle_codecs: list[str]
    decoded: bool
    windows_movies: bool
    vlc: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "container": self.container,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "subtitle_codecs": list(self.subtitle_codecs),
            "decoded": self.decoded,
            "windows_movies": self.windows_movies,
            "vlc": self.vlc,
            "notes": list(self.notes),
        }


def check_player_compatibility(path: Path, analyzer=None) -> CompatReport:
    source = path.expanduser().resolve()
    if not source.is_file() or source.stat().st_size < 32:
        raise ExportError(f"导出文件无效：{source}")
    if analyzer is None:
        from localvideoai.media.media_analyzer import MediaAnalyzer

        analyzer = MediaAnalyzer()
    analysis = analyzer.analyze(source)
    video = (analysis.primary_video.codec if analysis.primary_video else "").lower()
    audio = (analysis.audio_tracks[0].codec if analysis.audio_tracks else "").lower()
    subs = [(track.codec or track.format_name or "").lower() for track in analysis.subtitle_tracks]
    container = (analysis.format_name or source.suffix.lstrip(".")).lower()
    decoded = _decode_smoke(source)
    notes: list[str] = []
    windows = _windows_movies_ok(container, video, audio, subs, notes)
    vlc = decoded and bool(video)
    if not decoded:
        notes.append("FFmpeg 无法解码前 1 秒，播放器可能打不开")
    if container in {"matroska", "mkv"}:
        notes.append("MKV 内嵌字幕：Windows 影片和电视支持弱，VLC / PotPlayer 更稳")
    if container == "webm":
        notes.append("WebM + WebVTT：Chrome / VLC 可用，Windows 影片和电视通常不认")
    if "mov_text" in subs or "tx3g" in subs:
        notes.append("MP4 mov_text 轨道可被多数系统播放器识别")
    return CompatReport(
        path=source,
        container=container,
        video_codec=video,
        audio_codec=audio,
        subtitle_codecs=subs,
        decoded=decoded,
        windows_movies=windows,
        vlc=vlc,
        notes=notes,
    )


def _windows_movies_ok(container: str, video: str, audio: str, subs: list[str], notes: list[str]) -> bool:
    ok_container = container in {"mp4", "mov", "isom"} or "mp4" in container
    ok_video = video in {"h264", "avc", "hevc", "h265"}
    ok_audio = audio in {"", "aac", "mp3"}
    if not ok_container or not ok_video:
        return False
    if subs and not any(item in {"mov_text", "tx3g"} for item in subs):
        notes.append("内嵌字幕不是 mov_text，Windows 内置播放器可能看不到字幕")
        return False
    return ok_audio


def _decode_smoke(path: Path) -> bool:
    command = [
        str(find_ffmpeg()),
        "-hide_banner",
        "-v",
        "error",
        "-i",
        str(path),
        "-t",
        "1",
        "-f",
        "null",
        "-",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return completed.returncode == 0
