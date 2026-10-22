from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from localvideoai.core.types import VideoProbeResult
from localvideoai.engines.base import BaseEngine


class VideoEngine(BaseEngine):
    """Probe and transform video locally. Playback is streamed by PlaybackController."""

    @abstractmethod
    def probe(self, path: Path) -> VideoProbeResult:
        """Read container metadata without loading the whole file. Must not upload."""

    @abstractmethod
    def extract_audio(self, path: Path, destination: Path) -> Path:
        """Extract an audio track to a local file."""

    @abstractmethod
    def extract_frames(self, path: Path, destination_dir: Path, fps: float) -> list[Path]:
        """Extract frames for OCR / hard-subtitle analysis."""
