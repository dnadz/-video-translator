from __future__ import annotations

from abc import abstractmethod

from localvideoai.core.types import TranslationRequest, TranslationResult
from localvideoai.engines.base import BaseEngine


class TranslationEngine(BaseEngine):
    """Local machine translation. Model weights are loaded via ModelManager."""

    @abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate text with a local model. Must not call an online API."""

    def translate_document(self, document, source_lang, target_langs, **kwargs):
        from localvideoai.translation.document import translate_document

        return translate_document(self, document, source_lang, target_langs, **kwargs)
