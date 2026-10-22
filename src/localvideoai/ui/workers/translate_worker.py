from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import TranslationError
from localvideoai.engines.translation_engine import TranslationEngine
from localvideoai.subtitles.document import SubtitleDocument


class TranslateWorker(QThread):
    """Runs TranslationEngine off the UI thread. Does not import CTranslate2."""

    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        engine: TranslationEngine,
        document: SubtitleDocument,
        source_lang: str,
        target_langs: list[str],
        quality: str,
        device_preference: str,
        prefer_gpu: bool,
        parent: QObject | None = None,
        batch_size: int = 1,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._document = document
        self._source_lang = source_lang
        self._target_langs = list(target_langs)
        self._quality = quality
        self._device_preference = device_preference
        self._prefer_gpu = prefer_gpu
        self._batch_size = max(1, int(batch_size))

    def run(self) -> None:
        try:
            if hasattr(self._engine, "translate_document"):
                results = self._engine.translate_document(
                    self._document,
                    self._source_lang,
                    self._target_langs,
                    quality=self._quality,
                    device_preference=self._device_preference,
                    prefer_gpu=self._prefer_gpu,
                    progress=self._on_progress,
                    batch_size=self._batch_size,
                )
            else:
                from localvideoai.translation.document import translate_document

                results = translate_document(
                    self._engine,
                    self._document,
                    self._source_lang,
                    self._target_langs,
                    quality=self._quality,
                    device_preference=self._device_preference,
                    prefer_gpu=self._prefer_gpu,
                    progress=self._on_progress,
                    batch_size=self._batch_size,
                )
        except TranslationError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"本地翻译失败：{exc}")
            return
        if not results:
            self.failed.emit("没有可翻译的字幕（空文本或全部锁定）")
            return
        self.succeeded.emit(self._document)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progressChanged.emit(current, total, message)
