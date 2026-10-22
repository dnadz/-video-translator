from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from localvideoai.media.waveform import WaveformPeaks


class WaveformWidget(QWidget):
    seekRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("waveformWidget")
        self.setMinimumHeight(56)
        self.setToolTip("音频波形。点击跳转播放位置。")
        self._peaks: tuple[float, ...] = ()
        self._duration_ms = 0
        self._position_ms = 0
        self._message = "打开视频后显示音频波形"

    def set_peaks(self, peaks: WaveformPeaks | None) -> None:
        if peaks is None:
            self._peaks = ()
            self._duration_ms = 0
            self._message = "打开视频后显示音频波形"
        else:
            self._peaks = peaks.peaks
            self._duration_ms = peaks.duration_ms
            self._message = peaks.message or ("无音轨" if not peaks.peaks else "")
        self.update()

    def set_duration_ms(self, duration_ms: int) -> None:
        if duration_ms > 0:
            self._duration_ms = int(duration_ms)
        self.update()

    def set_position_ms(self, position_ms: int) -> None:
        self._position_ms = max(0, int(position_ms))
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.seekRequested.emit(self._x_to_ms(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e1e22"))
        width = max(1, self.width())
        height = max(1, self.height())
        mid = height // 2
        if self._peaks:
            count = len(self._peaks)
            pen = QPen(QColor("#7ad0a0"))
            painter.setPen(pen)
            for x in range(width):
                index = min(count - 1, int(x * count / width))
                amplitude = int(self._peaks[index] * (mid - 3))
                painter.drawLine(x, mid - amplitude, x, mid + amplitude)
        elif self._message:
            painter.setPen(QColor("#c8c8c8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
        if self._duration_ms > 0:
            x = int(self._position_ms * (width - 1) / self._duration_ms)
            painter.setPen(QPen(QColor("#ffcc66"), 1))
            painter.drawLine(x, 0, x, height)
        painter.end()

    def _x_to_ms(self, x: float) -> int:
        if self._duration_ms <= 0:
            return 0
        ratio = min(1.0, max(0.0, x / max(1, self.width())))
        return int(ratio * self._duration_ms)
