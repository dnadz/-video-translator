"""Runs hard-subtitle processing off the UI thread. Does not import model SDKs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import InpaintError
from localvideoai.engines.inpainting_engine import InpaintingEngine
from localvideoai.inpaint.types import InpaintResult
from localvideoai.ocr.region import NormalizedRegion
from localvideoai.subtitles.document import SubtitleDocument


class InpaintWorker(QThread):
    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        engine: InpaintingEngine,
        video_path: Path,
        destination: Path,
        mode: str,
        document: SubtitleDocument | None,
        language: str | None,
        region: NormalizedRegion | None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._video_path = video_path
        self._destination = destination
        self._mode = mode
        self._document = document
        self._language = language
        self._region = region

    def run(self) -> None:
        process = getattr(self._engine, "process_video", None)
        if process is None:
            self.failed.emit("当前引擎没有硬字幕处理方法")
            return
        try:
            result = process(
                self._video_path,
                self._destination,
                mode=self._mode,
                document=self._document,
                language=self._language,
                region=self._region,
                progress=self._on_progress,
            )
        except InpaintError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"本地硬字幕处理失败：{exc}")
            return
        if not isinstance(result, InpaintResult) or not result.output_path.is_file():
            self.failed.emit("硬字幕处理没有生成视频文件")
            return
        self.succeeded.emit(result)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progressChanged.emit(current, total, message)
