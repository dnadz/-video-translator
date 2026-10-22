from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from localvideoai.ui import strings


def format_clock(ms: int) -> str:
    total = max(0, int(ms) // 1000)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class TimelinePanel(QWidget):
    playClicked = Signal()
    pauseClicked = Signal()
    stopClicked = Signal()
    skipBackwardClicked = Signal()
    skipForwardClicked = Signal()
    seekRequested = Signal(int)
    volumeChanged = Signal(int)
    muteToggled = Signal(bool)
    rateChanged = Signal(float)
    fullscreenClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("timelinePanel")
        self.setMinimumHeight(104)
        self.setMaximumHeight(136)
        self._duration_ms = 0
        self._sliding = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)
        caption = QLabel("时间轴")
        caption.setObjectName("iosSectionHeader")
        self.hint_label = QLabel(strings.TIMELINE_HINT)
        self.hint_label.setObjectName("timelineHint")
        self.hint_label.setWordWrap(True)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("timelineSlider")
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.setEnabled(False)
        self.slider.setToolTip("请先打开视频")
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("timelineTimeLabel")
        transport = QHBoxLayout()
        self.play_button = QPushButton(strings.PLAY)
        self.play_button.setObjectName("playButton")
        self.pause_button = QPushButton("暂停")
        self.pause_button.setObjectName("pauseButton")
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stopButton")
        self.back_button = QPushButton("快退")
        self.back_button.setObjectName("skipBackButton")
        self.forward_button = QPushButton("快进")
        self.forward_button.setObjectName("skipForwardButton")
        self.mute_button = QPushButton("静音")
        self.mute_button.setObjectName("muteButton")
        self.mute_button.setCheckable(True)
        self.fullscreen_button = QPushButton("全屏")
        self.fullscreen_button.setObjectName("fullscreenButton")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setMaximumWidth(140)
        self.rate_combo = QComboBox()
        self.rate_combo.setObjectName("rateCombo")
        for rate in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            self.rate_combo.addItem(f"{rate:g}x", rate)
        self.rate_combo.setCurrentIndex(2)
        for button in (
            self.play_button,
            self.pause_button,
            self.stop_button,
            self.back_button,
            self.forward_button,
            self.mute_button,
            self.fullscreen_button,
        ):
            button.setEnabled(False)
            button.setToolTip("请先打开视频")
        self.play_button.clicked.connect(self.playClicked.emit)
        self.pause_button.clicked.connect(self.pauseClicked.emit)
        self.stop_button.clicked.connect(self.stopClicked.emit)
        self.back_button.clicked.connect(self.skipBackwardClicked.emit)
        self.forward_button.clicked.connect(self.skipForwardClicked.emit)
        self.mute_button.toggled.connect(self.muteToggled.emit)
        self.fullscreen_button.clicked.connect(self.fullscreenClicked.emit)
        self.volume_slider.valueChanged.connect(self.volumeChanged.emit)
        self.rate_combo.currentIndexChanged.connect(self._emit_rate)
        transport.addWidget(self.play_button)
        transport.addWidget(self.pause_button)
        transport.addWidget(self.stop_button)
        transport.addWidget(self.back_button)
        transport.addWidget(self.forward_button)
        transport.addWidget(self.time_label)
        transport.addStretch(1)
        transport.addWidget(QLabel("音量"))
        transport.addWidget(self.volume_slider)
        transport.addWidget(self.mute_button)
        transport.addWidget(QLabel("倍速"))
        transport.addWidget(self.rate_combo)
        transport.addWidget(self.fullscreen_button)
        layout.addWidget(caption)
        layout.addLayout(transport)
        layout.addWidget(self.slider)
        layout.addWidget(self.hint_label)

    def set_media_ready(self, ready: bool, message: str | None = None) -> None:
        for widget in (
            self.play_button,
            self.pause_button,
            self.stop_button,
            self.back_button,
            self.forward_button,
            self.mute_button,
            self.fullscreen_button,
            self.slider,
            self.volume_slider,
            self.rate_combo,
        ):
            widget.setEnabled(ready)
            widget.setToolTip("" if ready else "请先打开视频")
        if message:
            self.hint_label.setText(message)
        elif ready:
            self.hint_label.setText("流式播放。拖动进度条会跳转，不会重新加载整个文件。")
        else:
            self.hint_label.setText(strings.TIMELINE_HINT)

    def set_duration_ms(self, duration_ms: int) -> None:
        self._duration_ms = max(0, int(duration_ms))
        self.slider.setRange(0, self._duration_ms or 1000)
        self._refresh_time(self.slider.value())

    def set_position_ms(self, position_ms: int) -> None:
        if self._sliding:
            return
        self.slider.blockSignals(True)
        self.slider.setValue(max(0, int(position_ms)))
        self.slider.blockSignals(False)
        self._refresh_time(position_ms)

    def _refresh_time(self, position_ms: int) -> None:
        self.time_label.setText(f"{format_clock(position_ms)} / {format_clock(self._duration_ms)}")

    def _on_slider_pressed(self) -> None:
        self._sliding = True

    def _on_slider_moved(self, value: int) -> None:
        self._refresh_time(value)
        self.seekRequested.emit(int(value))

    def _on_slider_released(self) -> None:
        self._sliding = False
        self.seekRequested.emit(int(self.slider.value()))

    def _emit_rate(self) -> None:
        rate = self.rate_combo.currentData()
        if rate is not None:
            self.rateChanged.emit(float(rate))
