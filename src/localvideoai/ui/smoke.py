from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from localvideoai.core.paths import install_root
from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.ui.main_window import MainWindow, PAGES


def _grab(window: MainWindow, app: QApplication, destination: Path) -> None:
    for _ in range(8):
        app.processEvents()
    pixmap = window.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Window grab failed: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(destination)):
        raise RuntimeError(f"Cannot write screenshot: {destination}")


def run_ui_smoke(
    settings: SettingsManager,
    report: EnvironmentReport,
    output_dir: Path | None = None,
) -> dict[str, str]:
    """Exercise start, maximize, resize, all pages, Chinese paths, save, close, restart."""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication must exist before UI smoke.")
    output_dir = output_dir or (install_root() / "docs" / "phase1_artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)
    notes: dict[str, str] = {}

    window = MainWindow(settings, report)
    window.show()
    app.processEvents()
    notes["start_title"] = window.windowTitle()
    notes["start_visible"] = str(window.isVisible() or window.windowTitle() != "")
    _grab(window, app, output_dir / "01_start.png")

    window.showMaximized()
    app.processEvents()
    notes["maximized"] = str(bool(window.windowState() & Qt.WindowState.WindowMaximized) or window.isMaximized())
    _grab(window, app, output_dir / "02_maximized.png")

    window.showMinimized()
    app.processEvents()
    notes["minimized"] = str(bool(window.windowState() & Qt.WindowState.WindowMinimized) or window.isMinimized())
    window.showNormal()
    app.processEvents()

    window.resize(1100, 720)
    app.processEvents()
    notes["resized_1100"] = f"{window.width()}x{window.height()}"
    _grab(window, app, output_dir / "03_resized_1100.png")
    window.resize(1440, 900)
    app.processEvents()
    notes["resized_1440"] = f"{window.width()}x{window.height()}"
    notes["left_width"] = str(window.project_list.width())
    notes["right_width"] = str(window.side_panel.width())
    notes["timeline_height"] = str(window.timeline.height())
    _grab(window, app, output_dir / "04_resized_1440.png")

    chinese_dir = output_dir / "中文路径_测试"
    chinese_dir.mkdir(exist_ok=True)
    video = chinese_dir / "测试视频.mp4"
    subtitle = chinese_dir / "测试字幕.srt"
    video.write_bytes(b"")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试\n", encoding="utf-8")
    project_dir = chinese_dir / "测试项目"
    window.new_project("中文项目", project_dir)
    window.add_video_path(video)
    window.add_subtitle_path(subtitle)
    window.save_project()
    notes["chinese_project"] = str(window.project_path())
    notes["chinese_name"] = str(window.project_data().get("name"))
    _grab(window, app, output_dir / "05_chinese_paths.png")

    for index, (page_id, title) in enumerate(PAGES, start=6):
        window.switch_page(page_id)
        app.processEvents()
        if window.current_page_id() != page_id:
            raise RuntimeError(f"Page switch failed: {page_id}")
        _grab(window, app, output_dir / f"{index:02d}_page_{page_id}.png")
        notes[f"page_{page_id}"] = title

    window.apply_theme_preference("dark")
    app.processEvents()
    _grab(window, app, output_dir / "12_theme_dark.png")
    window.apply_theme_preference("light")
    window.save_user_settings()
    notes["menus"] = ",".join(window.menu_titles())
    notes["locked_translate"] = str(not window.side_panel.translate_button.isEnabled())
    notes["player_ready_without_media"] = str(not window.timeline.play_button.isEnabled())

    window.close()
    app.processEvents()
    notes["closed"] = str(not window.isVisible())

    restarted = MainWindow(settings, report)
    restarted.show()
    app.processEvents()
    notes["restart_page"] = restarted.current_page_id()
    notes["restart_theme"] = str(settings.get("app.theme"))
    _grab(restarted, app, output_dir / "13_restart.png")
    restarted.close()
    app.processEvents()
    return notes
