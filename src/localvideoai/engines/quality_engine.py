from __future__ import annotations

from abc import abstractmethod

from localvideoai.core.types import SubtitleCue
from localvideoai.engines.base import BaseEngine
from localvideoai.quality.types import QualityReport
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.resources import TranslationResources


class QualityEngine(BaseEngine):
    """Score subtitle timing, readability, and translation consistency."""

    @abstractmethod
    def score(self, cues: list[SubtitleCue]) -> dict[str, float]:
        """Return named quality metrics. Must not fabricate random scores."""

    @abstractmethod
    def inspect_document(
        self,
        document: SubtitleDocument,
        *,
        resources: TranslationResources | None = None,
        apply_fixes: bool = False,
    ) -> QualityReport:
        """Run deterministic QA on a document. Must not invent scores."""
