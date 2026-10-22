from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import SpeechError
from localvideoai.engines.speech_engine import SpeechEngine
from localvideoai.engines.translation_engine import TranslationEngine
from localvideoai.realtime.pipeline import process_realtime_window


class RealtimeWorker(QThread):
    """Runs one extract→ASR→translate window off the UI thread."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        speech_engine: SpeechEngine,
        translation_engine: TranslationEngine,
        media_path: Path,
        start_ms: int,
        requested_ms: int,
        source_lang: str,
        target_lang: str,
        profile: str,
        device_preference: str,
        prefer_gpu: bool,
        last_process_ms: int | None,
        duration_ms: int | None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._speech = speech_engine
        self._translation = translation_engine
        self._media_path = media_path
        self._start_ms = start_ms
        self._requested_ms = requested_ms
        self._source_lang = source_lang
        self._target_lang = target_lang
        self._profile = profile
        self._device_preference = device_preference
        self._prefer_gpu = prefer_gpu
        self._last_process_ms = last_process_ms
        self._duration_ms = duration_ms

    def run(self) -> None:
        try:
            cue = process_realtime_window(
                self._media_path,
                self._start_ms,
                self._requested_ms,
                speech_engine=self._speech,
                translation_engine=self._translation,
                source_lang=self._source_lang,
                target_lang=self._target_lang,
                profile=self._profile,
                device_preference=self._device_preference,
                prefer_gpu=self._prefer_gpu,
                last_process_ms=self._last_process_ms,
                duration_ms=self._duration_ms,
            )
        except SpeechError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"实时翻译失败：{exc}")
            return
        self.succeeded.emit(cue)
