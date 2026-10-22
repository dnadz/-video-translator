from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from localvideoai.speaker.labels import SPEAKER_STYLE_TABLE, apply_speaker_rename, default_style_id
from localvideoai.subtitles.document import SubtitleDocument


class SpeakerMapDialog(QDialog):
    """Rename Speaker 1/2/3 and assign subtitle styles. Local only."""

    def __init__(self, document: SubtitleDocument, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("speakerMapDialog")
        self.setWindowTitle("人物映射")
        self.resize(520, 320)
        self._document = document
        layout = QVBoxLayout(self)
        hint = QLabel("把 Speaker 1 改成真实人名后写入字幕。样式会按人物保存，下次打开仍在。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("speakerMapTable")
        self.table.setHorizontalHeaderLabels(["说话人", "显示名", "样式"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        layout.addLayout(row)
        self._load()

    def _load(self) -> None:
        ids: list[str] = []
        for segment in self._document.segments:
            canonical = str(segment.extra.get("speaker_id") or "").strip()
            if canonical and canonical not in ids:
                ids.append(canonical)
        if not ids:
            ids = ["Speaker 1", "Speaker 2", "Speaker 3"]
        self.table.setRowCount(len(ids))
        styles = [name for name, _color in SPEAKER_STYLE_TABLE]
        for row, canonical in enumerate(ids):
            display = self._document.speaker_map.get(canonical) or canonical
            style = self._document.speaker_styles.get(canonical) or default_style_id(canonical)
            locked = QTableWidgetItem(canonical)
            locked.setFlags(locked.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, locked)
            self.table.setItem(row, 1, QTableWidgetItem(display))
            self.table.setItem(row, 2, QTableWidgetItem(style if style in styles else styles[min(row, len(styles) - 1)]))

    def apply_to_document(self) -> None:
        for row in range(self.table.rowCount()):
            canonical_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            style_item = self.table.item(row, 2)
            if canonical_item is None:
                continue
            apply_speaker_rename(
                self._document,
                canonical_item.text().strip(),
                (name_item.text() if name_item else "").strip(),
                (style_item.text() if style_item else "").strip(),
            )
