from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from localvideoai.core.types import SubtitleSegment

EDGE_PX = 6
MIN_WIDTH_PX = 8


class SubtitleTimelineWidget(QWidget):
    seekRequested = Signal(int)
    cueSelected = Signal(int)
    cueDragStarted = Signal()
    cueTimesChanged = Signal(int, int, int)
    cueDragFinished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("subtitleTimeline")
        self.setMinimumHeight(72)
        self.setToolTip("字幕时间轴。拖动色块移动，拖边缘改时间。")
        self._segments: list[SubtitleSegment] = []
        self._duration_ms = 1000
        self._position_ms = 0
        self._selected = -1
        self._drag_mode = ""
        self._drag_index = -1
        self._drag_origin_x = 0
        self._drag_start = 0
        self._drag_end = 0

    def set_segments(self, segments: list[SubtitleSegment]) -> None:
        self._segments = list(segments)
        self.update()

    def set_duration_ms(self, duration_ms: int) -> None:
        self._duration_ms = max(1, int(duration_ms))
        self.update()

    def set_position_ms(self, position_ms: int) -> None:
        self._position_ms = max(0, int(position_ms))
        self.update()

    def set_selected(self, index: int) -> None:
        self._selected = int(index)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        x = event.position().x()
        hit = self._hit(x)
        if hit is None:
            self.seekRequested.emit(self._x_to_ms(x))
            event.accept()
            return
        index, mode = hit
        self._selected = index
        self.cueSelected.emit(index)
        segment = self._segments[index]
        if segment.locked:
            event.accept()
            return
        self._drag_mode = mode
        self._drag_index = index
        self._drag_origin_x = x
        self._drag_start = segment.start_time
        self._drag_end = segment.end_time
        self.cueDragStarted.emit()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._drag_mode or self._drag_index < 0:
            super().mouseMoveEvent(event)
            return
        delta = self._x_to_ms(event.position().x()) - self._x_to_ms(self._drag_origin_x)
        start, end = self._drag_start, self._drag_end
        if self._drag_mode == "move":
            span = end - start
            start = max(0, start + delta)
            end = start + span
        elif self._drag_mode == "start":
            start = min(end - 40, max(0, start + delta))
        elif self._drag_mode == "end":
            end = max(start + 40, end + delta)
        self.cueTimesChanged.emit(self._drag_index, start, end)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_mode:
            self._drag_mode = ""
            self._drag_index = -1
            self.cueDragFinished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#252528"))
        width = max(1, self.width())
        height = max(1, self.height())
        duration = max(1, self._duration_ms)
        font = QFont(self.font())
        font.setPointSize(max(7, font.pointSize() - 2))
        painter.setFont(font)
        for index, segment in enumerate(self._segments):
            rect = self._cue_rect(segment, width, height, duration)
            if rect.right() < 0 or rect.left() > width:
                continue
            if segment.locked:
                fill = QColor("#8a6a3b")
            elif index == self._selected:
                fill = QColor("#3d7ec9")
            else:
                fill = QColor("#3d5a80")
            painter.fillRect(rect, fill)
            painter.setPen(QColor("#dce8f5"))
            painter.drawRect(rect)
            label = (segment.display_text() or "（空）").replace("\n", " ")
            painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, label)
        x = int(self._position_ms * (width - 1) / duration)
        painter.setPen(QPen(QColor("#ffcc66"), 1))
        painter.drawLine(x, 0, x, height)
        painter.end()

    def _cue_rect(self, segment: SubtitleSegment, width: int, height: int, duration: int) -> QRect:
        left = int(segment.start_time * width / duration)
        right = int(segment.end_time * width / duration)
        if right - left < MIN_WIDTH_PX:
            right = left + MIN_WIDTH_PX
        return QRect(left, 10, max(MIN_WIDTH_PX, right - left), height - 20)

    def _hit(self, x: float) -> tuple[int, str] | None:
        duration = max(1, self._duration_ms)
        width = max(1, self.width())
        height = self.height()
        for index in range(len(self._segments) - 1, -1, -1):
            rect = self._cue_rect(self._segments[index], width, height, duration)
            if not (rect.left() - 1 <= x <= rect.right() + 1):
                continue
            if x <= rect.left() + EDGE_PX:
                return index, "start"
            if x >= rect.right() - EDGE_PX:
                return index, "end"
            return index, "move"
        return None

    def _x_to_ms(self, x: float) -> int:
        ratio = min(1.0, max(0.0, x / max(1, self.width())))
        return int(ratio * max(1, self._duration_ms))
