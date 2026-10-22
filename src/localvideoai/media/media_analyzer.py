from __future__ import annotations

from pathlib import Path

from localvideoai.core.exceptions import MediaError
from localvideoai.core.types import MediaAnalysis
from localvideoai.media.ffmpeg_probe import analyze_with_ffmpeg, analyze_with_ffprobe
from localvideoai.media.ffmpeg_runtime import find_ffprobe
from localvideoai.managers.log_manager import get_logger
from localvideoai.performance.cache import get_media_cache, media_cache_key


class MediaAnalyzer:
    """Read container metadata with bundled FFmpeg. Does not load the whole file into RAM."""

    def __init__(self) -> None:
        self._logger = get_logger("media")
        self._cache = get_media_cache()

    def analyze(self, path: Path) -> MediaAnalysis:
        source = path.expanduser().resolve()
        if not source.exists():
            raise MediaError(f"无法读取视频：文件不存在：{source}")
        if not source.is_file():
            raise MediaError(f"无法读取视频：不是文件：{source}")
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise MediaError(f"无法读取视频：无法访问文件：{source}") from exc
        if size <= 0:
            raise MediaError(f"无法读取视频：文件为空：{source}")
        key = media_cache_key(source)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        analysis = self._probe(source)
        self._cache.put(key, analysis)
        self._logger.info(
            "Analyzed %s size=%s duration_ms=%s video=%s audio=%s subtitles=%s embedded=%s",
            source,
            analysis.size_bytes,
            analysis.duration_ms,
            len(analysis.video_tracks),
            len(analysis.audio_tracks),
            len(analysis.subtitle_tracks),
            analysis.has_embedded_subtitles,
        )
        return analysis

    def _probe(self, source: Path) -> MediaAnalysis:
        try:
            find_ffprobe()
        except MediaError:
            return analyze_with_ffmpeg(source)
        try:
            return analyze_with_ffprobe(source)
        except MediaError as exc:
            self._logger.warning("ffprobe failed, falling back to ffmpeg -i: %s", exc)
            return analyze_with_ffmpeg(source)
