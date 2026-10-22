from __future__ import annotations

from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from localvideoai.ui.panels.subtitle_timeline import SubtitleTimelineWidget
from localvideoai.ui.panels.waveform_widget import WaveformWidget


class EditorTracksPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("editorTracksPanel")
        self.setMinimumHeight(140)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        self.waveform_label = QLabel("音频波形")
        self.waveform = WaveformWidget()
        self.timeline_label = QLabel("字幕时间轴")
        self.cue_timeline = SubtitleTimelineWidget()
        self.waveform.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.cue_timeline.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.waveform_label)
        layout.addWidget(self.waveform, 1)
        layout.addWidget(self.timeline_label)
        layout.addWidget(self.cue_timeline, 1)
