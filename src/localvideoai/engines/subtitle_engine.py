from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from localvideoai.core.types import EmbeddedSubtitleTrack, SubtitleSegment
from localvideoai.engines.base import BaseEngine
from localvideoai.subtitles.document import SubtitleDocument


class SubtitleEngine(BaseEngine):
    """Read and write external files and extract embedded subtitle tracks."""

    @abstractmethod
    def load(self, path: Path) -> list[SubtitleSegment]:
        """Load SRT/ASS/SSA/VTT from disk into SubtitleSegment rows."""

    @abstractmethod
    def save(self, segments: list[SubtitleSegment], path: Path, fmt: str) -> Path:
        """Write subtitles to disk."""

    @abstractmethod
    def list_embedded(self, video_path: Path) -> list[str]:
        """List embedded subtitle stream identifiers."""

    @abstractmethod
    def list_embedded_tracks(self, video_path: Path) -> list[EmbeddedSubtitleTrack]:
        """List every embedded subtitle track with language and readability."""

    @abstractmethod
    def extract_embedded(
        self, video_path: Path, stream_index: int, destination: Path | None = None
    ) -> list[SubtitleSegment]:
        """Extract one embedded track into SubtitleSegment rows."""

    @abstractmethod
    def extract_embedded_document(
        self, video_path: Path, stream_index: int, destination: Path | None = None
    ) -> SubtitleDocument:
        """Extract one embedded track into the internal subtitle document."""

    @abstractmethod
    def preview_embedded(self, video_path: Path, stream_index: int, max_cues: int = 40) -> SubtitleDocument:
        """Extract a preview document without requiring a destination file."""
