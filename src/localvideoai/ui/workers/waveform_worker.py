from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from localvideoai.core.exceptions import MediaError
from localvideoai.media.waveform import extract_waveform_peaks


class WaveformWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, media_path, parent=None) -> None:
        super().__init__(parent)
        self._path = media_path

    def run(self) -> None:
        try:
            peaks = extract_waveform_peaks(self._path, should_cancel=self.isInterruptionRequested)
        except MediaError as exc:
            if "已取消" in str(exc) or self.isInterruptionRequested():
                return
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"波形提取失败：{exc}")
            return
        self.succeeded.emit(peaks)
