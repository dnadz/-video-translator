from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent, QKeyEvent
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QGridLayout, QLabel, QStackedLayout, QVBoxLayout, QWidget

from localvideoai.media.playback_controller import collect_video_paths
from localvideoai.ui import strings


class _FullscreenHost(QWidget):
    def __init__(self, stage: "VideoStage") -> None:
        super().__init__(None)
        self._stage = stage
        self.setObjectName("videoFullscreenHost")
        self.setWindowTitle("全屏播放")
        self._content = QVBoxLayout(self)
        self._content.setContentsMargins(0, 0, 0, 0)
        self._content.setSpacing(0)
        self.caption = QLabel("")
        self.caption.setObjectName("realtimeFullscreenCaption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.caption.setWordWrap(True)

    def attach(self, widget: QWidget) -> None:
        if self._content.indexOf(widget) < 0:
            self._content.insertWidget(0, widget)
        if self._content.indexOf(self.caption) < 0:
            self._content.addWidget(self.caption)
        self._content.setStretch(0, 1)
        self._content.setStretch(1, 0)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._stage.exit_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stage.exit_fullscreen()
        event.accept()


class VideoStage(QWidget):
    filesDropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("videoStage")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(strings.VIDEO_STAGE_EMPTY)
        self.title_label.setObjectName("videoStageTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        self.path_label = QLabel("")
        self.path_label.setObjectName("videoStagePath")
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.path_label.setWordWrap(True)
        self.hint_label = QLabel(strings.VIDEO_STAGE_HINT)
        self.hint_label.setObjectName("videoStageHint")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setWordWrap(True)
        self.video_widget = QVideoWidget()
        self.video_widget.setObjectName("videoWidget")
        self.caption_overlay = QLabel("")
        self.caption_overlay.setObjectName("realtimeCaption")
        self.caption_overlay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.caption_overlay.setWordWrap(True)
        self.caption_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.video_host = QWidget()
        self.video_host.setObjectName("videoHost")
        host_layer = QGridLayout(self.video_host)
        host_layer.setContentsMargins(0, 0, 0, 0)
        host_layer.addWidget(self.video_widget, 0, 0)
        host_layer.addWidget(self.caption_overlay, 0, 0)
        self.caption_overlay.raise_()
        self.placeholder = QWidget()
        placeholder_layout = QVBoxLayout(self.placeholder)
        placeholder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(self.title_label)
        placeholder_layout.addWidget(self.path_label)
        placeholder_layout.addWidget(self.hint_label)
        self.stack = QStackedLayout()
        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.video_host)
        self.caption_bar = QLabel("")
        self.caption_bar.setObjectName("realtimeCaptionBar")
        self.caption_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_bar.setWordWrap(True)
        self.caption_bar.setMinimumHeight(36)
        self.caption_bar.hide()
        layout.addLayout(self.stack, 1)
        layout.addWidget(self.caption_bar, 0)
        self._fullscreen_host: _FullscreenHost | None = None
        self._realtime_session = False

    def show_media(self, path: str | None) -> None:
        if not path:
            self.title_label.setText(strings.VIDEO_STAGE_EMPTY)
            self.path_label.setText("")
            self.hint_label.setText(strings.VIDEO_STAGE_HINT)
            if not self.is_fullscreen():
                self.stack.setCurrentWidget(self.placeholder)
            return
        name = Path(path).name
        self.title_label.setText(strings.VIDEO_STAGE_SELECTED.format(name=name))
        self.path_label.setText(path)
        self.hint_label.setText("流式播放中。不会把整个文件读进内存。")
        if not self.is_fullscreen():
            self.stack.setCurrentWidget(self.video_host)

    def show_placeholder_message(self, message: str) -> None:
        self.hint_label.setText(message)
        if not self.is_fullscreen():
            self.stack.setCurrentWidget(self.placeholder)

    def enter_fullscreen(self) -> None:
        if self.is_fullscreen():
            return
        if self._fullscreen_host is None:
            self._fullscreen_host = _FullscreenHost(self)
        host = self._fullscreen_host
        self.video_widget.setParent(None)
        host.attach(self.video_widget)
        host.caption.setText(self.caption_overlay.text())
        host.showFullScreen()
        self.video_widget.show()
        self.video_widget.setFocus()

    def exit_fullscreen(self) -> None:
        host = self._fullscreen_host
        if host is None or not host.isVisible():
            if self.video_widget.parent() is None:
                self.video_host.layout().addWidget(self.video_widget, 0, 0)
            return
        self.video_widget.setParent(None)
        layout = self.video_host.layout()
        layout.addWidget(self.video_widget, 0, 0)
        layout.addWidget(self.caption_overlay, 0, 0)
        self.caption_overlay.raise_()
        self.stack.setCurrentWidget(self.video_host)
        host.hide()

    def set_realtime_active(self, active: bool) -> None:
        self._realtime_session = bool(active)
        self.caption_bar.setVisible(self._realtime_session)
        if not active:
            self.set_realtime_caption("")

    def set_realtime_caption(self, text: str) -> None:
        display = (text or "").strip()
        self.caption_overlay.setText(display)
        if self._realtime_session:
            self.caption_bar.setText(display or "实时翻译进行中…")
            self.caption_bar.show()
        else:
            self.caption_bar.setText(display)
            self.caption_bar.setVisible(bool(display))
        host = self._fullscreen_host
        if host is not None:
            host.caption.setText(display)

    def is_fullscreen(self) -> bool:
        host = self._fullscreen_host
        return bool(host is not None and host.isFullScreen() and host.isVisible())

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [str(path) for path in collect_video_paths(list(event.mimeData().urls()))]
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
        else:
            event.ignore()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.is_fullscreen():
            self.exit_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)
