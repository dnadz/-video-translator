from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QGroupBox, QLabel, QTextEdit, QVBoxLayout, QWidget

from localvideoai.core.types import MediaAnalysis
from localvideoai.media.media_format import format_audio_section, format_subtitle_section, format_video_section


@dataclass
class _Section:
    box: QGroupBox
    editor: QTextEdit


class MediaInfoPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mediaInfoPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("打开视频后自动分析容器信息。只读本地文件，不会上传。")
        hint.setWordWrap(True)
        self.video_section = self._section("视频信息", "mediaVideoInfo")
        self.audio_section = self._section("音频信息", "mediaAudioInfo")
        self.subtitle_section = self._section("字幕信息", "mediaSubtitleInfo")
        layout.addWidget(hint)
        layout.addWidget(self.video_section.box, 1)
        layout.addWidget(self.audio_section.box, 1)
        layout.addWidget(self.subtitle_section.box, 1)
        self.clear()

    @property
    def video_info(self) -> QTextEdit:
        return self.video_section.editor

    @property
    def audio_info(self) -> QTextEdit:
        return self.audio_section.editor

    @property
    def subtitle_info(self) -> QTextEdit:
        return self.subtitle_section.editor

    def _section(self, title: str, object_name: str) -> _Section:
        box = QGroupBox(title)
        inner = QVBoxLayout(box)
        editor = QTextEdit()
        editor.setObjectName(object_name)
        editor.setReadOnly(True)
        inner.addWidget(editor)
        return _Section(box=box, editor=editor)

    def clear(self) -> None:
        self.video_info.setPlainText("尚未打开视频。")
        self.audio_info.setPlainText("尚未打开视频。")
        self.subtitle_info.setPlainText("尚未打开视频。")

    def set_analysis(self, analysis: MediaAnalysis) -> None:
        self.video_info.setPlainText(format_video_section(analysis))
        self.audio_info.setPlainText(format_audio_section(analysis))
        self.subtitle_info.setPlainText(format_subtitle_section(analysis))

    def set_error(self, message: str) -> None:
        text = message.strip() or "无法读取视频。"
        self.video_info.setPlainText(text)
        self.audio_info.setPlainText("无法显示音频信息，因为视频未能读取。")
        self.subtitle_info.setPlainText("无法显示字幕信息，因为视频未能读取。")
