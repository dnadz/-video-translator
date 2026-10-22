from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from localvideoai.core.exceptions import MediaError
from localvideoai.managers.log_manager import get_logger

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m4v", ".mpeg", ".mpg"}


def collect_video_paths(urls: list) -> list[Path]:
    paths: list[Path] = []
    for url in urls:
        local = url.toLocalFile() if hasattr(url, "toLocalFile") else str(url)
        if not local:
            continue
        path = Path(local)
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            paths.append(path)
    return paths


class PlaybackController(QObject):
    """Streamed local playback via Qt Multimedia (FFmpeg backend). Never slurps the file."""

    positionChanged = Signal(int)
    durationChanged = Signal(int)
    stateChanged = Signal(str)
    errorOccurred = Signal(str)
    mediaOpened = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._logger = get_logger("playback")
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.8)
        self._muted_volume = 0.8
        self._path: Path | None = None
        self._updating_slider = False
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.errorOccurred.connect(self._on_error)

    @property
    def player(self) -> QMediaPlayer:
        return self._player

    @property
    def audio(self) -> QAudioOutput:
        return self._audio

    @property
    def source_path(self) -> Path | None:
        return self._path

    def set_video_output(self, output: object) -> None:
        self._player.setVideoOutput(output)

    def open(self, path: Path, autoplay: bool = True) -> None:
        source = path.expanduser().resolve()
        if not source.is_file():
            raise MediaError(f"视频不存在：{source}")
        if source.stat().st_size <= 0:
            raise MediaError(f"视频文件为空：{source}")
        self.stop()
        self._path = source
        url = QUrl.fromLocalFile(str(source))
        self._player.setSource(url)
        self.mediaOpened.emit(str(source))
        self._logger.info("Open streamed source %s (%s bytes)", source, source.stat().st_size)
        if autoplay:
            self.play()

    def play(self) -> None:
        if self._path is None:
            raise MediaError("尚未打开视频")
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()
        self._player.setPosition(0)

    def seek_ms(self, position_ms: int) -> None:
        duration = max(0, int(self._player.duration()))
        target = max(0, position_ms)
        if duration:
            target = min(target, duration)
        self._player.setPosition(target)

    def skip_ms(self, delta_ms: int) -> None:
        self.seek_ms(int(self._player.position()) + delta_ms)

    def set_rate(self, rate: float) -> None:
        if rate <= 0:
            raise MediaError("倍速必须大于 0")
        self._player.setPlaybackRate(rate)

    def set_volume(self, volume: float) -> None:
        value = min(1.0, max(0.0, volume))
        self._audio.setVolume(value)
        if value > 0:
            self._muted_volume = value
            self._audio.setMuted(False)

    def set_muted(self, muted: bool) -> None:
        if muted:
            if not self._audio.isMuted():
                self._muted_volume = self._audio.volume()
            self._audio.setMuted(True)
        else:
            self._audio.setMuted(False)
            if self._audio.volume() <= 0:
                self._audio.setVolume(self._muted_volume or 0.8)

    def is_muted(self) -> bool:
        return bool(self._audio.isMuted())

    def volume(self) -> float:
        return float(self._audio.volume())

    def rate(self) -> float:
        return float(self._player.playbackRate() or 1.0)

    def position_ms(self) -> int:
        return int(self._player.position())

    def duration_ms(self) -> int:
        return int(self._player.duration())

    def state_name(self) -> str:
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            return "playing"
        if state == QMediaPlayer.PlaybackState.PausedState:
            return "paused"
        return "stopped"

    def close(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())
        self._path = None

    def _on_position(self, position: int) -> None:
        self.positionChanged.emit(int(position))

    def _on_duration(self, duration: int) -> None:
        self.durationChanged.emit(int(duration))

    def _on_state(self, _state: QMediaPlayer.PlaybackState) -> None:
        self.stateChanged.emit(self.state_name())

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        text = message or str(error)
        self._logger.error("Playback error: %s", text)
        self.errorOccurred.emit(text)
