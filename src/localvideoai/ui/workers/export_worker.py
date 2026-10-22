from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import ExportError
from localvideoai.core.types import ExportRequest
from localvideoai.engines.export_engine import ExportEngine
from localvideoai.engines.ffmpeg_export_engine import FFmpegExportEngine


class ExportWorker(QThread):
    """Runs export off the UI thread. Does not import model SDKs."""

    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, engine: ExportEngine, request: ExportRequest, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._request = request

    def run(self) -> None:
        try:
            detailed = getattr(self._engine, "export_detailed", None)
            if detailed is None:
                path = self._engine.export(self._request)
                self.succeeded.emit(path)
                return
            result = detailed(self._request, progress=self._on_progress)
        except ExportError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"导出失败：{exc}")
            return
        self.succeeded.emit(result)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progressChanged.emit(current, total, message)
