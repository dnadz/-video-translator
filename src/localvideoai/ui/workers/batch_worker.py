"""Runs BatchRunner off the UI thread. Does not import model SDKs."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import TaskError


class BatchWorker(QThread):
    changed = Signal()
    failed = Signal(str)
    finishedIdle = Signal()

    def __init__(self, runner, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runner = runner

    def run(self) -> None:
        previous = getattr(self._runner, "_on_change", None)
        self._runner._on_change = self.changed.emit
        try:
            self._runner.run_until_idle()
        except TaskError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"批量处理失败：{exc}")
        finally:
            self._runner._on_change = previous
            self.changed.emit()
            self.finishedIdle.emit()
