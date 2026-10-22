from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget


class ProjectPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("projectPage")
        self.form = QFormLayout(self)
        self.form.setContentsMargins(20, 16, 20, 16)
        self.form.setSpacing(10)
        title = QLabel("项目")
        title.setObjectName("iosLargeTitle")
        self.form.addRow(title)
        self.name_label = QLabel("—")
        self.name_label.setObjectName("projectNameLabel")
        self.path_label = QLabel("—")
        self.path_label.setObjectName("projectPathLabel")
        self.path_label.setWordWrap(True)
        self.counts_label = QLabel("—")
        self.counts_label.setObjectName("projectCountsLabel")
        hint = QLabel("新建 / 打开 / 保存使用顶部「项目」菜单。项目文件扩展名是 .vtproj（UTF-8 JSON），支持中文路径。关闭后可恢复全部状态；异常退出可在启动时选择恢复 / 放弃 / 保存。")
        hint.setWordWrap(True)
        self.form.addRow("项目名称", self.name_label)
        self.form.addRow("项目文件", self.path_label)
        self.form.addRow("内容", self.counts_label)
        self.form.addRow(hint)

    def set_project(self, name: str, path: Path | None, video_count: int, subtitle_count: int) -> None:
        self.name_label.setText(name)
        self.path_label.setText(str(path) if path else "尚未保存到磁盘")
        self.counts_label.setText(f"视频 {video_count} 个，字幕 {subtitle_count} 个")
