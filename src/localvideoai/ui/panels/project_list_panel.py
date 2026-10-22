from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from localvideoai.ui import strings


class ProjectListPanel(QWidget):
    selection_changed = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("projectListPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        caption = QLabel(strings.LIST_HINT)
        caption.setObjectName("iosSectionHeader")
        caption.setWordWrap(True)
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("projectMediaList")
        self.list_widget.currentItemChanged.connect(self._emit_selection)
        layout.addWidget(caption)
        layout.addWidget(self.list_widget, 1)

    def set_items(self, videos: list[dict], subtitles: list[dict]) -> None:
        self.list_widget.clear()
        for item in videos:
            self._add_row("video", item)
        for item in subtitles:
            self._add_row("subtitle", item)

    def _add_row(self, kind: str, item: dict) -> None:
        path = item.get("path", "")
        name = item.get("name") or Path(path).name
        prefix = "视频" if kind == "video" else "字幕"
        row = QListWidgetItem(f"[{prefix}] {name}")
        row.setData(int(Qt.ItemDataRole.UserRole), kind)
        row.setData(int(Qt.ItemDataRole.UserRole) + 1, path)
        row.setToolTip(path)
        self.list_widget.addItem(row)

    def selected_path(self) -> tuple[str | None, str | None]:
        row = self.list_widget.currentItem()
        if row is None:
            return None, None
        return str(row.data(int(Qt.ItemDataRole.UserRole))), str(row.data(int(Qt.ItemDataRole.UserRole) + 1))

    def _emit_selection(self) -> None:
        kind, path = self.selected_path()
        self.selection_changed.emit(kind or "", path or "")
