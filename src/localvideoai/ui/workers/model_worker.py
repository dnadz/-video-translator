from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import ModelError
from localvideoai.managers.local_model_manager import LocalModelManager


class ModelWorker(QThread):
    """Runs model install/import off the UI thread. Does not import model SDKs."""

    progressChanged = Signal(int, int, str)
    succeeded = Signal(str, object)
    failed = Signal(str)

    def __init__(
        self,
        manager: LocalModelManager,
        action: str,
        model_id: str | None = None,
        source: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._action = action
        self._model_id = model_id
        self._source = source

    def run(self) -> None:
        try:
            if self._action == "install":
                if not self._model_id:
                    raise ModelError("没有选择要安装的模型")
                path = self._manager.install(self._model_id, progress=self._on_progress)
            elif self._action == "import":
                if self._source is None:
                    raise ModelError("没有选择要导入的目录")
                path = self._manager.import_local(self._source, self._model_id, progress=self._on_progress)
            else:
                raise ModelError(f"未知模型操作：{self._action}")
        except ModelError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"模型操作失败：{exc}")
            return
        self.succeeded.emit(self._action, path)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progressChanged.emit(current, total, message)
