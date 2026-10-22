from __future__ import annotations

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from localvideoai.core.paths import install_root
from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.ui.main_window import MainWindow


def _wait(app: QApplication, predicate, timeout_ms: int = 8000) -> bool:
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(40)
    timer.timeout.connect(lambda: predicate() and loop.quit())
    fail = QTimer()
    fail.setSingleShot(True)
    fail.timeout.connect(loop.quit)
    timer.start()
    fail.start(timeout_ms)
    loop.exec()
    timer.stop()
    return bool(predicate())


def run_player_smoke(settings: SettingsManager, report: EnvironmentReport) -> dict[str, str]:
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication must exist before player smoke.")
    window = MainWindow(settings, report)
    window.show()
    app.processEvents()
    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    chinese = install_root() / "test_assets" / "videos" / "中文路径" / "10秒_测试.mp4"
    notes: dict[str, str] = {"video": str(video), "exists": str(video.is_file())}
    window.add_video_path(video)
    if not _wait(app, lambda: window.playback.duration_ms() >= 9000):
        raise RuntimeError(f"duration not ready: {window.playback.duration_ms()}")
    notes["duration"] = str(window.playback.duration_ms())
    notes["playing"] = window.playback.state_name()
    window.playback.pause()
    app.processEvents()
    notes["paused"] = window.playback.state_name()
    window.playback.seek_ms(3500)
    _wait(app, lambda: abs(window.playback.position_ms() - 3500) < 1500)
    notes["seeked"] = str(window.playback.position_ms())
    window.playback.set_rate(1.25)
    window.playback.set_volume(0.4)
    notes["rate"] = str(window.playback.player.playbackRate())
    notes["volume"] = str(round(window.playback.volume(), 2))
    window.video_stage.enter_fullscreen()
    if not _wait(app, lambda: window.video_stage.is_fullscreen()):
        raise RuntimeError("fullscreen did not activate")
    notes["fullscreen"] = str(window.video_stage.is_fullscreen())
    window.video_stage.exit_fullscreen()
    _wait(app, lambda: not window.video_stage.is_fullscreen())
    notes["fullscreen_exited"] = str(not window.video_stage.is_fullscreen())
    window.playback.close()
    window.add_video_path(chinese)
    _wait(app, lambda: window.playback.duration_ms() >= 9000)
    notes["chinese"] = str(window.playback.source_path)
    notes["reopened"] = window.playback.state_name()
    window.close()
    app.processEvents()
    return notes
