from __future__ import annotations

import ctypes
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtMultimedia import QMediaPlayer

from localvideoai.core.paths import install_root
from localvideoai.engines.ffmpeg_video_engine import FFmpegVideoEngine
from localvideoai.media.ffmpeg_runtime import find_ffmpeg
from localvideoai.media.playback_controller import PlaybackController


def _wait(qt_app, predicate, timeout_ms: int = 8000) -> bool:
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(50)

    def tick() -> None:
        if predicate():
            loop.quit()

    timer.timeout.connect(tick)
    fail = QTimer()
    fail.setSingleShot(True)
    fail.timeout.connect(loop.quit)
    timer.start()
    fail.start(timeout_ms)
    loop.exec()
    timer.stop()
    return bool(predicate())


def _process_memory() -> tuple[int, int]:
    """Return (working_set, private_bytes). Private bytes exclude file-cache mappings."""

    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    fn = ctypes.windll.kernel32.K32GetProcessMemoryInfo
    fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX), ctypes.c_ulong]
    fn.restype = ctypes.c_int
    if not fn(handle, ctypes.byref(counters), counters.cb):
        raise OSError(f"K32GetProcessMemoryInfo failed: {ctypes.GetLastError()}")
    return int(counters.WorkingSetSize), int(counters.PrivateUsage)


def test_ffmpeg_is_bundled():
    exe = find_ffmpeg()
    assert exe.is_file()
    assert "WindowsApps" not in str(exe)


def test_probe_does_not_require_loading_whole_file():
    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    assert video.is_file()
    info = FFmpegVideoEngine().probe(video)
    assert info.duration_ms >= 9000
    assert info.width == 1280
    assert info.height == 720
    assert any(stream.kind == "video" for stream in info.streams)
    assert any(stream.kind == "audio" for stream in info.streams)


def test_play_pause_seek_rate_volume(qt_app, main_window):
    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    main_window.add_video_path(video)
    player = main_window.playback
    assert _wait(qt_app, lambda: player.duration_ms() >= 9000)
    assert _wait(
        qt_app,
        lambda: player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
    )
    assert player.position_ms() >= 0
    player.pause()
    qt_app.processEvents()
    assert player.state_name() == "paused"
    paused_at = player.position_ms()
    player.seek_ms(4000)
    assert _wait(qt_app, lambda: abs(player.position_ms() - 4000) < 1200)
    player.skip_ms(2000)
    assert _wait(qt_app, lambda: player.position_ms() >= 5000)
    player.set_rate(1.5)
    assert abs(player.player.playbackRate() - 1.5) < 0.01
    player.set_volume(0.35)
    assert abs(player.volume() - 0.35) < 0.05
    player.set_muted(True)
    assert player.is_muted()
    player.set_muted(False)
    assert not player.is_muted()
    player.play()
    assert _wait(qt_app, lambda: player.state_name() == "playing")
    player.stop()
    qt_app.processEvents()
    assert player.state_name() == "stopped"
    assert paused_at >= 0
    assert main_window.timeline.slider.isEnabled()
    assert main_window.timeline.play_button.isEnabled()


def test_chinese_path_playback(qt_app, main_window):
    video = install_root() / "test_assets" / "videos" / "中文路径" / "10秒_测试.mp4"
    main_window.add_video_path(video)
    assert _wait(qt_app, lambda: main_window.playback.duration_ms() >= 9000)
    assert main_window.playback.source_path is not None
    assert "中文路径" in str(main_window.playback.source_path)


def test_format_matrix_opens(qt_app, main_window):
    folder = install_root() / "test_assets" / "videos"
    files = [
        folder / "10秒_测试.mp4",
        folder / "格式测试.mkv",
        folder / "格式测试.mov",
        folder / "格式测试.avi",
        folder / "格式测试.webm",
        folder / "高分辨率_1080p.mp4",
    ]
    for path in files:
        assert path.is_file(), path
        main_window.add_video_path(path)
        assert _wait(qt_app, lambda p=path: main_window.playback.source_path == p.resolve())
        assert _wait(qt_app, lambda: main_window.playback.duration_ms() > 0), path.name
        main_window.playback.stop()


def test_fullscreen_toggle(qt_app, main_window):
    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    main_window.add_video_path(video)
    main_window.video_stage.enter_fullscreen()
    qt_app.processEvents()
    assert main_window.video_stage.is_fullscreen()
    main_window.video_stage.exit_fullscreen()
    qt_app.processEvents()
    assert not main_window.video_stage.is_fullscreen()


def test_close_and_reopen(qt_app, main_window):
    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    main_window.add_video_path(video)
    assert _wait(qt_app, lambda: main_window.playback.duration_ms() >= 9000)
    main_window.playback.close()
    qt_app.processEvents()
    assert main_window.playback.source_path is None
    main_window.add_video_path(video)
    assert _wait(qt_app, lambda: main_window.playback.state_name() == "playing")


def test_drop_video_on_stage(qt_app, main_window):
    from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
    from PySide6.QtGui import QDropEvent

    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(video.resolve()))])
    event = QDropEvent(
        QPointF(12, 12),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    main_window.video_stage.dropEvent(event)
    assert _wait(qt_app, lambda: main_window.playback.duration_ms() >= 9000)
    assert main_window.playback.source_path == video.resolve()


def test_long_video_does_not_load_entire_file(qt_app, main_window):
    folder = install_root() / "test_assets" / "videos"
    short = folder / "10秒_测试.mp4"
    video = folder / "10分钟_测试.mp4"
    assert short.is_file() and video.is_file()
    size_short = short.stat().st_size
    size = video.stat().st_size
    assert size > size_short * 5
    assert size > 1_000_000

    main_window.playback.close()
    qt_app.processEvents()
    _, baseline_short = _process_memory()
    main_window.add_video_path(short)
    assert _wait(qt_app, lambda: main_window.playback.duration_ms() >= 9000)
    assert _wait(qt_app, lambda: main_window.playback.position_ms() >= 400)
    _, after_short = _process_memory()
    short_private = after_short - baseline_short

    main_window.playback.close()
    qt_app.processEvents()
    _, baseline_long = _process_memory()
    main_window.add_video_path(video)
    assert _wait(qt_app, lambda: main_window.playback.duration_ms() >= 590_000, timeout_ms=15000)
    assert _wait(qt_app, lambda: main_window.playback.position_ms() >= 800, timeout_ms=8000)
    _, after_play = _process_memory()
    main_window.playback.seek_ms(300_000)
    assert _wait(qt_app, lambda: abs(main_window.playback.position_ms() - 300_000) < 4000, timeout_ms=8000)
    ws_seek, after_seek = _process_memory()
    long_private = max(after_play, after_seek) - baseline_long
    seek_private_delta = after_seek - after_play

    assert long_private < short_private + 40_000_000, (
        f"10-minute clip private={long_private} vs 10-second clip private={short_private}; "
        f"file sizes {size} vs {size_short}. Memory scaled with file size, indicating a full-file load."
    )
    assert long_private < size + 16_000_000, (
        f"private memory grew {long_private} bytes while the 10-minute file is {size} bytes"
    )
    assert seek_private_delta < 20_000_000, (
        f"seek to 5:00 grew private memory by {seek_private_delta}; streaming seek should not load the rest of the file"
    )
    assert ws_seek > 0
    assert main_window.playback.duration_ms() >= 590_000
