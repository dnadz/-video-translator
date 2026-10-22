from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from localvideoai.ui import strings


def format_eta(seconds: int | None) -> str:
    if seconds is None:
        return "计算中"
    value = max(0, int(seconds))
    minutes, secs = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class BatchPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        hint = QLabel(
            "批量队列会真正跑分析、识别、OCR、翻译、校对和导出。"
            "完成的任务自动跳过。关闭软件会保存状态，再次打开可继续。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("batchHint")

        buttons = QHBoxLayout()
        self.add_button = QPushButton("添加文件到队列")
        self.add_button.setObjectName("batchAddButton")
        self.start_button = QPushButton(strings.START_BATCH)
        self.start_button.setObjectName("batchStartButton")
        self.pause_button = QPushButton(strings.PAUSE_BATCH)
        self.pause_button.setObjectName("batchPauseButton")
        self.resume_button = QPushButton(strings.RESUME_BATCH)
        self.resume_button.setObjectName("batchResumeButton")
        self.cancel_button = QPushButton(strings.CANCEL_BATCH)
        self.cancel_button.setObjectName("batchCancelButton")
        self.retry_button = QPushButton(strings.RETRY_BATCH)
        self.retry_button.setObjectName("batchRetryButton")
        self.remove_button = QPushButton(strings.DELETE_BATCH)
        self.remove_button.setObjectName("batchRemoveButton")
        for widget in (
            self.add_button,
            self.start_button,
            self.pause_button,
            self.resume_button,
            self.cancel_button,
            self.retry_button,
            self.remove_button,
        ):
            buttons.addWidget(widget)
        buttons.addStretch(1)

        controls = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setObjectName("batchDeviceCombo")
        self.device_combo.addItem(strings.DEVICE_AUTO, "auto")
        self.device_combo.addItem(strings.DEVICE_CPU, "cpu")
        self.device_combo.addItem(strings.DEVICE_GPU, "gpu")
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setObjectName("batchConcurrentSpin")
        self.concurrent_spin.setRange(1, 4)
        self.concurrent_spin.setValue(1)
        self.cpu_spin = QSpinBox()
        self.cpu_spin.setObjectName("batchCpuSpin")
        self.cpu_spin.setRange(0, 64)
        self.cpu_spin.setSpecialValueText("自动")
        self.cpu_spin.setValue(0)
        self.ram_spin = QDoubleSpinBox()
        self.ram_spin.setObjectName("batchRamSpin")
        self.ram_spin.setRange(0.0, 256.0)
        self.ram_spin.setDecimals(1)
        self.ram_spin.setSingleStep(0.5)
        self.ram_spin.setSpecialValueText("自动")
        self.ram_spin.setValue(0.0)
        controls.addWidget(QLabel("设备"))
        controls.addWidget(self.device_combo)
        controls.addWidget(QLabel("并发"))
        controls.addWidget(self.concurrent_spin)
        controls.addWidget(QLabel("CPU 线程"))
        controls.addWidget(self.cpu_spin)
        controls.addWidget(QLabel("内存上限 GB"))
        controls.addWidget(self.ram_spin)
        controls.addStretch(1)

        self.stats_label = QLabel("尚未开始")
        self.stats_label.setObjectName("batchStatsLabel")
        self.stats_label.setWordWrap(True)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("batchTable")
        self.table.setHorizontalHeaderLabels(["文件名", "状态", "阶段", "输出", "路径"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(hint)
        layout.addLayout(buttons)
        layout.addLayout(controls)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.table, 1)

    def set_items(self, items: list[dict]) -> None:
        selected = set(self.selected_task_ids())
        self.table.setRowCount(len(items))
        for index, item in enumerate(items):
            path = item.get("path", "")
            name_item = QTableWidgetItem(item.get("name") or Path(str(path)).name)
            name_item.setData(Qt.ItemDataRole.UserRole, item.get("task_id") or item.get("id") or "")
            self.table.setItem(index, 0, name_item)
            self.table.setItem(index, 1, QTableWidgetItem(item.get("status", "等待")))
            self.table.setItem(index, 2, QTableWidgetItem(str(item.get("stage") or item.get("current_stage") or "")))
            output = item.get("export_video_path") or item.get("export_path") or ""
            self.table.setItem(index, 3, QTableWidgetItem(str(output)))
            self.table.setItem(index, 4, QTableWidgetItem(str(path)))
            if name_item.data(Qt.ItemDataRole.UserRole) in selected:
                self.table.selectRow(index)

    def selected_task_ids(self) -> list[str]:
        ids: list[str] = []
        for index in {item.row() for item in self.table.selectedItems()}:
            cell = self.table.item(index, 0)
            if cell is None:
                continue
            task_id = str(cell.data(Qt.ItemDataRole.UserRole) or "")
            if task_id:
                ids.append(task_id)
        return ids

    def set_stats(self, stats: dict) -> None:
        device = str(stats.get("device") or "auto")
        gpu = "优先 GPU" if stats.get("prefer_gpu") else "CPU"
        speed = float(stats.get("speed_per_min") or 0.0)
        eta = format_eta(stats.get("eta_seconds"))
        self.stats_label.setText(
            f"CPU {stats.get('cpu_count', 0)} 核 / 线程 {stats.get('cpu_threads', 0) or '自动'}  |  "
            f"设备 {device}（{gpu}）  |  "
            f"RAM 可用 {stats.get('available_ram_gb', 0)} / {stats.get('total_ram_gb', 0)} GB  |  "
            f"并发 {stats.get('max_concurrent', 1)}  |  "
            f"运行 {stats.get('running', 0)}  |  "
            f"完成 {stats.get('done', 0)}/{stats.get('total', 0)}  |  "
            f"速度 {speed:.2f} 个/分  |  "
            f"预计剩余 {eta}"
        )
