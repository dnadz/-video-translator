from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from localvideoai.subtitles.operations import TEXT_FIELDS

FIELD_CHOICES = (
    ("全部", TEXT_FIELDS),
    ("原文", ("source_text",)),
    ("校正", ("corrected_text",)),
    ("译文", ("translated_text",)),
)


class FindReplaceDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("findReplaceDialog")
        self.setWindowTitle("查找 / 替换")
        self.resize(420, 200)
        self._hits: list[tuple[int, str]] = []
        self._cursor = -1
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setObjectName("findEdit")
        self.replace_edit = QLineEdit()
        self.replace_edit.setObjectName("replaceEdit")
        self.field_combo = QComboBox()
        self.field_combo.setObjectName("findFieldCombo")
        for label, _fields in FIELD_CHOICES:
            self.field_combo.addItem(label)
        form.addRow("查找", self.find_edit)
        form.addRow("替换为", self.replace_edit)
        form.addRow("范围", self.field_combo)
        layout.addLayout(form)
        self.status_label = QLabel("锁定条目不会被替换。")
        self.status_label.setObjectName("findStatusLabel")
        layout.addWidget(self.status_label)
        buttons = QHBoxLayout()
        self.find_button = QPushButton("查找下一个")
        self.find_button.setObjectName("findNextButton")
        self.replace_button = QPushButton("替换全部")
        self.replace_button.setObjectName("replaceAllButton")
        buttons.addWidget(self.find_button)
        buttons.addWidget(self.replace_button)
        layout.addLayout(buttons)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        box.accepted.connect(self.accept)
        layout.addWidget(box)

    def needle(self) -> str:
        return self.find_edit.text()

    def replacement(self) -> str:
        return self.replace_edit.text()

    def fields(self) -> tuple[str, ...]:
        return FIELD_CHOICES[self.field_combo.currentIndex()][1]

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
