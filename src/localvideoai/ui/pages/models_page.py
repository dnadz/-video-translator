from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from localvideoai.models.records import EMPTY_MODELS_HINT, ModelRecord
from localvideoai.ui import strings

COLUMNS = ("模型名称", "类型", "语言", "大小", "量化", "推荐RAM", "推荐显存", "状态")


class ModelsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modelsPage")
        self._records: list[ModelRecord] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        self.hint = QLabel(
            "模型写入独立目录，不占用软件安装目录。可导入本机已部署模型，或按 CPU/GPU/RAM/VRAM 推荐安装小模型。"
        )
        self.hint.setWordWrap(True)
        self.hint.setObjectName("modelsHint")
        self.empty_label = QLabel(EMPTY_MODELS_HINT)
        self.empty_label.setWordWrap(True)
        self.empty_label.setObjectName("modelsEmptyLabel")
        self.empty_label.setVisible(False)
        self.recommend_label = QLabel("")
        self.recommend_label.setWordWrap(True)
        self.recommend_label.setObjectName("modelsRecommendLabel")
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("模型目录"))
        self.dir_edit = QLineEdit()
        self.dir_edit.setObjectName("modelsDirEdit")
        self.dir_edit.setReadOnly(True)
        self.change_dir_button = QPushButton(strings.CHANGE_MODELS_DIR)
        self.change_dir_button.setObjectName("changeModelsDirButton")
        path_row.addWidget(self.dir_edit, 1)
        path_row.addWidget(self.change_dir_button)
        buttons = QHBoxLayout()
        self.install_button = QPushButton(strings.INSTALL_MODEL)
        self.install_button.setObjectName("downloadModelButton")
        self.download_button = self.install_button
        self.delete_button = QPushButton(strings.DELETE_MODEL)
        self.delete_button.setObjectName("deleteModelButton")
        self.switch_button = QPushButton(strings.SWITCH_MODEL)
        self.switch_button.setObjectName("switchModelButton")
        self.import_button = QPushButton(strings.IMPORT_MODEL)
        self.import_button.setObjectName("importModelButton")
        self.enable_button = QPushButton(strings.ENABLE_MODEL)
        self.enable_button.setObjectName("enableModelButton")
        self.disable_button = QPushButton(strings.DISABLE_MODEL)
        self.disable_button.setObjectName("disableModelButton")
        self.refresh_button = QPushButton(strings.REFRESH_MODELS)
        self.refresh_button.setObjectName("refreshModelsButton")
        for button in (
            self.install_button,
            self.delete_button,
            self.switch_button,
            self.import_button,
            self.enable_button,
            self.disable_button,
            self.refresh_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("localModelTable")
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.list_widget = self.table
        self.progress = QProgressBar()
        self.progress.setObjectName("modelsProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_label = QLabel("空闲")
        self.progress_label.setObjectName("modelsProgressLabel")
        layout.addWidget(self.hint)
        layout.addWidget(self.recommend_label)
        layout.addLayout(path_row)
        layout.addLayout(buttons)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.progress_label)

    def set_records(
        self,
        models_dir: Path,
        records: list[ModelRecord],
        *,
        recommend_reason: str = "",
        empty_hint: str = EMPTY_MODELS_HINT,
    ) -> None:
        self._records = list(records)
        self.dir_edit.setText(str(models_dir))
        self.recommend_label.setText(recommend_reason)
        installed = [item for item in records if item.installed]
        self.empty_label.setText(empty_hint)
        self.empty_label.setVisible(not installed)
        self.table.setVisible(True)
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = (
                record.name,
                record.type,
                record.languages,
                record.size_text(),
                record.quantization,
                record.ram_text(),
                record.vram_text(),
                record.status,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record.id)
                self.table.setItem(row, column, item)
        if records:
            self.table.selectRow(0)

    def set_models(self, models_dir: Path, names: list[str]) -> None:
        self.dir_edit.setText(str(models_dir))
        if not names:
            self.empty_label.setText(EMPTY_MODELS_HINT)
            self.empty_label.setVisible(True)
            self.table.setRowCount(0)
            return
        self.empty_label.setVisible(False)
        self.table.setRowCount(len(names))
        for row, name in enumerate(names):
            item = QTableWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.table.setItem(row, 0, item)

    def selected_record(self) -> ModelRecord | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def selected_model_id(self) -> str | None:
        record = self.selected_record()
        return record.id if record is not None else None

    def set_busy(self, busy: bool, message: str = "") -> None:
        for button in (
            self.install_button,
            self.delete_button,
            self.switch_button,
            self.import_button,
            self.enable_button,
            self.disable_button,
            self.change_dir_button,
        ):
            button.setEnabled(not busy)
        if message:
            self.progress_label.setText(message)

    def set_progress(self, current: int, total: int, message: str) -> None:
        maximum = max(1, total)
        self.progress.setMaximum(maximum)
        self.progress.setValue(min(current, maximum))
        self.progress_label.setText(message)
