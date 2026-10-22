from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from localvideoai.ocr.region import NormalizedRegion


class RegionPickerDialog(QDialog):
    """Rubber-band a still frame. Returns a normalized subtitle region."""

    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("框选硬字幕区域")
        self.setObjectName("ocrRegionPicker")
        self._origin: QPoint | None = None
        self._chosen: QRect | None = None
        layout = QVBoxLayout(self)
        hint = QLabel("在画面上拖拽鼠标框选字幕区域，然后确定。")
        hint.setWordWrap(True)
        self.image = QLabel()
        self.image.setObjectName("ocrRegionImage")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(image_path))
        if pixmap.width() > 960:
            pixmap = pixmap.scaledToWidth(960, Qt.TransformationMode.SmoothTransformation)
        self.image.setPixmap(pixmap)
        self.image.setFixedSize(pixmap.size())
        self.overlay = _RubberBand(self.image)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(hint)
        layout.addWidget(self.image, 1)
        layout.addWidget(buttons)

    def region(self) -> NormalizedRegion | None:
        rect = self.overlay.normalized_rect()
        if rect is None:
            return None
        return rect


class _RubberBand(QWidget):
    def __init__(self, parent: QLabel) -> None:
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self._start: QPoint | None = None
        self._rect = QRect()
        self.show()
        self.raise_()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._start = event.position().toPoint()
        self._rect = QRect(self._start, self._start)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start is None:
            return
        self._rect = QRect(self._start, event.position().toPoint()).normalized()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._start is None:
            return
        self._rect = QRect(self._start, event.position().toPoint()).normalized()
        self._start = None
        self.update()

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QColor, QPainter, QPen

        painter = QPainter(self)
        painter.setPen(QPen(QColor(80, 180, 255), 2))
        painter.setBrush(QColor(80, 180, 255, 40))
        if self._rect.isValid() and self._rect.width() > 4:
            painter.drawRect(self._rect)

    def normalized_rect(self) -> NormalizedRegion | None:
        parent = self.parentWidget()
        if parent is None or not self._rect.isValid() or self._rect.width() < 8:
            return None
        width = max(1, parent.width())
        height = max(1, parent.height())
        return NormalizedRegion(
            self._rect.x() / width,
            self._rect.y() / height,
            self._rect.width() / width,
            self._rect.height() / height,
        ).clamp()
