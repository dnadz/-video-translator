from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import SpeechError
from localvideoai.core.types import SpeechTranscript
from localvideoai.engines.speech_engine import SpeechEngine
from localvideoai.performance.throttle import ProgressThrottle


class TranscribeWorker(QThread):
    """Runs SpeechEngine off the UI thread. Does not import model SDKs."""

    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        engine: SpeechEngine,
        media_path: Path,
        language: str | None,
        device_preference: str,
        prefer_gpu: bool,
        parent: QObject | None = None,
        *,
        chunk_ms: int | None = None,
        overlap_ms: int | None = None,
        progress_min_interval_ms: int = 120,
        asr_batch_size: int = 0,
        beam_size: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._media_path = media_path
        self._language = language
        self._device_preference = device_preference
        self._prefer_gpu = prefer_gpu
        self._chunk_ms = chunk_ms
        self._overlap_ms = overlap_ms
        self._asr_batch_size = max(0, int(asr_batch_size))
        self._beam_size = beam_size
        self._throttle = ProgressThrottle(progress_min_interval_ms, self._emit_progress)

    def run(self) -> None:
        try:
            transcribe = getattr(self._engine, "transcribe_media")
            extra: dict[str, int] = {}
            if self._chunk_ms:
                extra["chunk_ms"] = self._chunk_ms
            if self._overlap_ms:
                extra["overlap_ms"] = self._overlap_ms
            if self._asr_batch_size:
                extra["asr_batch_size"] = self._asr_batch_size
            if self._beam_size:
                extra["beam_size"] = self._beam_size
            transcript = transcribe(
                self._media_path,
                language=self._language,
                device_preference=self._device_preference,
                prefer_gpu=self._prefer_gpu,
                progress=self._throttle,
                **extra,
            )
        except SpeechError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"本地语音识别失败：{exc}")
            return
        if not isinstance(transcript, SpeechTranscript):
            self.failed.emit("识别引擎没有返回有效结果")
            return
        self.succeeded.emit(transcript)

    def _emit_progress(self, current_ms: int, total_ms: int, message: str) -> None:
        self.progressChanged.emit(current_ms, total_ms, message)
