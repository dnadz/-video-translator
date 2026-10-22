from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from localvideoai.ui import strings


class ExportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, default_dir: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("exportDialog")
        self.setWindowTitle(strings.EXPORT)
        self.resize(520, 280)
        form = QFormLayout(self)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("exportModeCombo")
        self.mode_combo.addItem(strings.EXPORT_EMBED, "embed")
        self.mode_combo.addItem(strings.EXPORT_BURN_IN, "burn_in")
        self.mode_combo.addItem(strings.EXPORT_SIDECAR, "sidecar")
        self.mode_combo.addItem(strings.EXPORT_MULTILINGUAL, "multilingual")
        self.mode_combo.addItem(strings.EXPORT_PROJECT, "project")
        self.container_combo = QComboBox()
        self.container_combo.setObjectName("exportContainerCombo")
        self.container_combo.addItem("MP4", "mp4")
        self.container_combo.addItem("MKV", "mkv")
        self.container_combo.addItem("WebM", "webm")
        self.codec_combo = QComboBox()
        self.codec_combo.setObjectName("exportCodecCombo")
        self.codec_combo.addItem("复制（不重编码）", "copy")
        self.codec_combo.addItem("H.264", "h264")
        self.codec_combo.addItem("H.265", "h265")
        self.format_combo = QComboBox()
        self.format_combo.setObjectName("exportSubtitleFormatCombo")
        for label, value in (("SRT", "srt"), ("ASS", "ass"), ("SSA", "ssa"), ("VTT", "vtt")):
            self.format_combo.addItem(label, value)
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.path_edit = QLineEdit(default_dir)
        self.path_edit.setObjectName("exportPathEdit")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(browse)
        form.addRow("导出方式", self.mode_combo)
        form.addRow("容器", self.container_combo)
        form.addRow("视频编码", self.codec_combo)
        form.addRow("字幕格式", self.format_combo)
        form.addRow("输出", path_row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.mode_combo.currentIndexChanged.connect(self._sync_codec)

    def _sync_codec(self) -> None:
        if self.mode_combo.currentData() == "burn_in" and self.codec_combo.currentData() == "copy":
            index = self.codec_combo.findData("h264")
            if index >= 0:
                self.codec_combo.setCurrentIndex(index)

    def _browse(self) -> None:
        if self.mode_combo.currentData() == "project":
            picked = QFileDialog.getExistingDirectory(self, "选择项目导出目录", self.path_edit.text())
            if picked:
                self.path_edit.setText(picked)
            return
        suffix = self.container_combo.currentData() or "mp4"
        picked, _ = QFileDialog.getSaveFileName(
            self,
            "导出视频",
            self.path_edit.text(),
            f"视频 (*.{suffix});;所有文件 (*.*)",
        )
        if picked:
            self.path_edit.setText(picked)

    def values(self) -> dict[str, str]:
        return {
            "mode": str(self.mode_combo.currentData() or "embed"),
            "container": str(self.container_combo.currentData() or "mp4"),
            "video_codec": str(self.codec_combo.currentData() or "copy"),
            "subtitle_format": str(self.format_combo.currentData() or "srt"),
            "output": self.path_edit.text().strip(),
        }
