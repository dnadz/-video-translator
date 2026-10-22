from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from localvideoai.engines.base import BaseEngine


class InpaintingEngine(BaseEngine):
    """Remove hard subtitles from video frames locally."""

    @abstractmethod
    def remove_hard_subs(self, video_path: Path, destination: Path) -> Path:
        """Produce a local video with burned-in text removed. Must not upload video."""
