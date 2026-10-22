from __future__ import annotations

from pathlib import Path

from localvideoai.core.types import EmbeddedSubtitleTrack, SubtitleSegment
from localvideoai.engines.subtitle_engine import SubtitleEngine
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.extractor import (
    extract_embedded_track,
    list_embedded_tracks as scan_embedded_tracks,
    preview_embedded_track,
)
from localvideoai.subtitles.io import load_subtitle, save_subtitle


class FileSubtitleEngine(SubtitleEngine):
    """Read/write external subtitles and extract embedded text tracks."""

    def __init__(self) -> None:
        self._analyzer = MediaAnalyzer()

    @property
    def engine_id(self) -> str:
        return "file-subtitle"

    @property
    def display_name(self) -> str:
        return "File Subtitle Engine"

    def load(self, path: Path) -> list[SubtitleSegment]:
        return self.load_document(path).segments

    def load_document(self, path: Path) -> SubtitleDocument:
        return load_subtitle(path)

    def save(self, segments: list[SubtitleSegment], path: Path, fmt: str) -> Path:
        document = SubtitleDocument(segments=list(segments), format_name=fmt.lower())
        return save_subtitle(document, path, fmt)

    def save_document(self, document: SubtitleDocument, path: Path, fmt: str | None = None) -> Path:
        return save_subtitle(document, path, fmt)

    def list_embedded(self, video_path: Path) -> list[str]:
        return [track.label() for track in self.list_embedded_tracks(video_path)]

    def list_embedded_tracks(self, video_path: Path) -> list[EmbeddedSubtitleTrack]:
        return scan_embedded_tracks(video_path, analyzer=self._analyzer)

    def extract_embedded(
        self, video_path: Path, stream_index: int, destination: Path | None = None
    ) -> list[SubtitleSegment]:
        return self.extract_embedded_document(video_path, stream_index, destination).segments

    def extract_embedded_document(
        self, video_path: Path, stream_index: int, destination: Path | None = None
    ) -> SubtitleDocument:
        return extract_embedded_track(
            video_path,
            stream_index,
            destination=destination,
            analyzer=self._analyzer,
        )

    def preview_embedded(self, video_path: Path, stream_index: int, max_cues: int = 40) -> SubtitleDocument:
        return preview_embedded_track(video_path, stream_index, max_cues=max_cues, analyzer=self._analyzer)
