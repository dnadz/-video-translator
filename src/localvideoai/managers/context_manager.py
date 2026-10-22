from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from localvideoai.core.types import SubtitleCue

if TYPE_CHECKING:
    from localvideoai.translation.context import PreparedUtterance


class ContextManager(ABC):
    """Provide local context windows for translation without sending data off-machine."""

    @abstractmethod
    def build_context(self, cues: list[SubtitleCue], index: int) -> str:
        """Build surrounding dialogue context for a cue."""

    def chunk_ranges(self, count: int) -> list[range]:
        return [range(count)] if count else []

    def progress_label(self) -> str:
        return ""

    def note_source(self, text: str) -> None:
        return None

    def prepare(self, text: str, source_lang: str, target_lang: str, context: str = "") -> PreparedUtterance:
        from localvideoai.translation.context import PreparedUtterance

        return PreparedUtterance(
            text=text,
            original=text,
            context=context,
            force_terms=(),
            session_memory=(),
            applied=(),
            pronoun_rewritten=False,
        )

    def observe(self, original: str, rewritten: str, translated: str, target_lang: str) -> None:
        return None
