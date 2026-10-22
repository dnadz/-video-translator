from __future__ import annotations

from localvideoai.core.types import SubtitleCue
from localvideoai.managers.context_manager import ContextManager
from localvideoai.translation.context import PreparedUtterance, TranslationContextSession, window_policy
from localvideoai.translation.resources import ResourceEntry, TranslationResources


class LocalContextManager(ContextManager):
    """Concrete local context window + session memories. Does not call a cloud LLM."""

    def __init__(
        self,
        quality: str = "standard",
        *,
        resources: TranslationResources | None = None,
        extra_entries: list[ResourceEntry] | None = None,
        enabled: bool = True,
    ) -> None:
        self._session = TranslationContextSession(
            quality,
            resources=resources,
            extra_entries=extra_entries,
            enabled=enabled,
        )

    @property
    def policy(self):
        return self._session.policy

    @property
    def memory(self):
        return self._session.memory

    @property
    def enabled(self) -> bool:
        return self._session.enabled

    def build_context(self, cues: list[SubtitleCue], index: int) -> str:
        return self._session.build_context(cues, index)

    def chunk_ranges(self, count: int) -> list[range]:
        return self._session.chunk_ranges(count)

    def progress_label(self) -> str:
        return self._session.progress_label()

    def note_source(self, text: str) -> None:
        self._session.note_source(text)

    def prepare(self, text: str, source_lang: str, target_lang: str, context: str = "") -> PreparedUtterance:
        return self._session.prepare(text, source_lang, target_lang, context)

    def observe(self, original: str, rewritten: str, translated: str, target_lang: str) -> None:
        self._session.observe(original, rewritten, translated, target_lang)


def create_context_manager(
    quality: str = "standard",
    *,
    resources: TranslationResources | None = None,
    extra_entries: list[ResourceEntry] | None = None,
    enabled: bool = True,
) -> LocalContextManager:
    window_policy(quality)
    return LocalContextManager(
        quality,
        resources=resources,
        extra_entries=extra_entries,
        enabled=enabled,
    )
