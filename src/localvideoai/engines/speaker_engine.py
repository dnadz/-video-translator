from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from localvideoai.core.types import SpeechSegment
from localvideoai.engines.base import BaseEngine


class SpeakerEngine(BaseEngine):
    """Speaker diarization over local audio."""

    @abstractmethod
    def diarize(self, audio_path: Path) -> list[SpeechSegment]:
        """Assign speaker labels to time ranges. Must not upload audio."""
