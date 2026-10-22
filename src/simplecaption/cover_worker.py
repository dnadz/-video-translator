"""Blur burned-in subtitles off the UI thread."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import ExportError
from simplecaption.cover import cover_burned_subtitles


class CoverWorker(QThread):
    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, video: Path, subtitle: Path, destination: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._video = video
        self._subtitle = subtitle
        self._destination = destination

    def run(self) -> None:
        try:
            path = cover_burned_subtitles(
                self._video,
                self._subtitle,
                self._destination,
                progress=self._on_progress,
            )
        except ExportError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"模糊原字幕失败：{exc}")
            return
        self.succeeded.emit(path)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progressChanged.emit(current, total, "正在模糊底部原字幕")
