"""Rule-based quality engine. CPU-only, no model SDK, no random scores."""

from __future__ import annotations

from localvideoai.core.types import SubtitleCue
from localvideoai.engines.quality_engine import QualityEngine
from localvideoai.quality.pipeline import (
    confirm_cue as confirm_document_cue,
    inspect_document,
    lock_confirmed as lock_document_confirmed,
    score_cues,
)
from localvideoai.quality.types import QualityReport
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.resources import TranslationResources


class LocalQualityEngine(QualityEngine):
    """Deterministic broadcast-style QA over SubtitleDocument."""

    @property
    def engine_id(self) -> str:
        return "local-rule-quality"

    @property
    def display_name(self) -> str:
        return "Local Rule Quality Engine"

    def available(self) -> bool:
        return True

    def score(self, cues: list[SubtitleCue]) -> dict[str, float]:
        return score_cues(cues)

    def inspect_document(
        self,
        document: SubtitleDocument,
        *,
        resources: TranslationResources | None = None,
        apply_fixes: bool = False,
    ) -> QualityReport:
        return inspect_document(document, resources=resources, apply_fixes=apply_fixes)

    def confirm_cue(self, document: SubtitleDocument, index: int) -> None:
        confirm_document_cue(document, index)

    def lock_confirmed(self, document: SubtitleDocument) -> int:
        return lock_document_confirmed(document)
