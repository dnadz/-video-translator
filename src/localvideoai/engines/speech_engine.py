from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from localvideoai.core.types import SpeechSegment
from localvideoai.engines.base import BaseEngine


class SpeechEngine(BaseEngine):
    """Local speech recognition. Implementations must run on CPU and use GPU when available."""

    @abstractmethod
    def transcribe(self, audio_path: Path, language: str | None = None) -> list[SpeechSegment]:
        """Transcribe local audio or video soundtrack. Must not upload media."""
