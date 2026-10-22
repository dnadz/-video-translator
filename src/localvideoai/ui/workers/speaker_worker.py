from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from localvideoai.core.exceptions import MediaError, SpeakerError
from localvideoai.engines.speaker_engine import SpeakerEngine
from localvideoai.subtitles.document import SubtitleDocument


class SpeakerWorker(QThread):
    """Runs speaker diarization off the UI thread. Does not import model SDKs."""

    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        engine: SpeakerEngine,
        document: SubtitleDocument,
        media_path: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._document = document
        self._media_path = media_path

    def run(self) -> None:
        try:
            label = getattr(self._engine, "label_document")
            result = label(self._document, self._media_path, progress=self._on_progress)
        except SpeakerError as exc:
            self.failed.emit(str(exc))
            return
        except MediaError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"本地说话人分离失败：{exc}")
            return
        self.succeeded.emit(result)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progressChanged.emit(current, total, message)
