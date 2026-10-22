from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import OCRError
from localvideoai.core.types import OCRTranscript
from localvideoai.engines.ocr_engine import OCREngine
from localvideoai.ocr.region import NormalizedRegion
from localvideoai.performance.throttle import ProgressThrottle


class OCRWorker(QThread):
    """Runs OCREngine off the UI thread. Does not import RapidOCR."""

    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        engine: OCREngine,
        media_path: Path,
        language: str | None,
        region: NormalizedRegion | None,
        device_preference: str,
        prefer_gpu: bool,
        parent: QObject | None = None,
        *,
        sample_fps: float | None = None,
        progress_min_interval_ms: int = 120,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._media_path = media_path
        self._language = language
        self._region = region
        self._device_preference = device_preference
        self._prefer_gpu = prefer_gpu
        self._sample_fps = sample_fps
        self._throttle = ProgressThrottle(progress_min_interval_ms, self._emit_progress)

    def run(self) -> None:
        try:
            recognize = getattr(self._engine, "recognize_video")
            extra: dict[str, float] = {}
            if self._sample_fps:
                extra["sample_fps"] = self._sample_fps
            transcript = recognize(
                self._media_path,
                language=self._language,
                region=self._region,
                device_preference=self._device_preference,
                prefer_gpu=self._prefer_gpu,
                progress=self._throttle,
                **extra,
            )
        except OCRError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"本地硬字幕 OCR 失败：{exc}")
            return
        if not isinstance(transcript, OCRTranscript):
            self.failed.emit("OCR 引擎没有返回有效结果")
            return
        self.succeeded.emit(transcript)

    def _emit_progress(self, current_ms: int, total_ms: int, message: str) -> None:
        self.progressChanged.emit(current_ms, total_ms, message)
