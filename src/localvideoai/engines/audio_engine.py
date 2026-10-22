from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from localvideoai.engines.base import BaseEngine


class AudioEngine(BaseEngine):
    """Local audio extraction, resampling, and VAD helpers."""

    @abstractmethod
    def extract(self, media_path: Path, destination: Path) -> Path:
        """Extract audio from a media file to wav/flac locally."""

    @abstractmethod
    def resample(self, audio_path: Path, destination: Path, sample_rate: int) -> Path:
        """Resample audio for speech models."""
