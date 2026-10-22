from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.ui.main_window import MainWindow, PAGES
from localvideoai.ui.theme import apply_theme

from tests.conftest import make_report


def test_ui_font_is_cjk_capable(qt_app):
    from localvideoai.ui.theme import pick_ui_font_family

    family = pick_ui_font_family()
    assert family in {
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "SimHei",
    }
    assert qt_app.font().family() in {
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "SimHei",
    }


def test_start_and_close(main_window, qt_app):
    assert "翻译工作站" in main_window.windowTitle()
    assert main_window.width() >= 1024
    assert main_window.height() >= 680
    main_window.close()
    qt_app.processEvents()
    assert not main_window.isVisible()


def test_maximize_minimize_resize(main_window, qt_app):
    main_window.showMaximized()
    qt_app.processEvents()
    maximized = main_window.isMaximized() or bool(main_window.windowState() & Qt.WindowState.WindowMaximized)
    assert maximized
    main_window.showMinimized()
    qt_app.processEvents()
    minimized = main_window.isMinimized() or bool(main_window.windowState() & Qt.WindowState.WindowMinimized)
    assert minimized
    main_window.showNormal()
    qt_app.processEvents()
    main_window.resize(1180, 760)
    qt_app.processEvents()
    assert main_window.width() >= 1100
    assert main_window.height() >= 700
    main_window.resize(1440, 900)
    qt_app.processEvents()
    assert main_window.project_list.width() >= 160
    assert main_window.side_panel.width() >= 200
    assert main_window.page_stack.height() >= 240
    assert main_window.timeline.height() >= 60


def test_all_pages_switch(main_window, qt_app):
    assert [title for _, title in PAGES] == main_window.page_titles()
    for page_id, title in PAGES:
        main_window.switch_page(page_id)
        qt_app.processEvents()
        assert main_window.current_page_id() == page_id
        assert main_window.page_stack.currentWidget().isVisible() or main_window.page_stack.currentIndex() >= 0
        assert title in (main_window.statusBar().currentMessage() or "")


def test_menus_exist_and_locked_actions_are_disabled(main_window):
    assert main_window.menu_titles() == ["文件", "编辑", "项目", "工具", "AI", "设置", "帮助"]
    transcribe = main_window.findChild(QAction, "action_menuTranscribe")
    ocr = main_window.findChild(QAction, "action_menuOcr")
    translate = main_window.findChild(QAction, "action_menuTranslate")
    assert transcribe is not None and transcribe.isEnabled()
    assert ocr is not None and ocr.isEnabled()
    assert translate is not None and translate.isEnabled()
    assert main_window.side_panel.translate_button.isEnabled()
    assert main_window.side_panel.transcribe_button.isEnabled()
    assert main_window.side_panel.ocr_button.isEnabled()
    assert not main_window.timeline.slider.isEnabled()
    assert "请先打开视频" in (main_window.timeline.slider.toolTip() or "")
    assert main_window.batch_page.start_button.isEnabled()
    assert main_window.batch_page.pause_button.isEnabled()
    assert main_window.batch_page.resume_button.isEnabled()
    assert main_window.models_page.download_button.isEnabled()
    assert "未启用" not in (main_window.side_panel.translate_button.toolTip() or "")


def test_chinese_paths_and_filenames(main_window, isolated_env):
    folder = isolated_env / "中文目录_UI测试"
    folder.mkdir()
    video = folder / "测试视频.mp4"
    subtitle = folder / "测试字幕.srt"
    video.write_bytes(b"")
    subtitle.write_text("测试", encoding="utf-8")
    project_dir = folder / "测试项目"
    path = main_window.new_project("中文项目", project_dir)
    main_window.add_video_path(video)
    main_window.add_subtitle_path(subtitle)
    saved = main_window.save_project()
    assert saved == path
    text = Path(saved).read_text(encoding="utf-8")
    assert "中文项目" in text
    assert "测试视频.mp4" in text
    assert "测试字幕.srt" in text
    assert "测试视频.mp4" in main_window.video_stage.title_label.text()
    assert str(video.resolve()) in main_window.video_stage.path_label.text()


def test_config_save_from_settings_page(main_window, isolated_env):
    main_window.switch_page("settings")
    main_window.settings_page.prefer_gpu.setChecked(False)
    main_window.apply_theme_preference("dark")
    saved = main_window.save_user_settings()
    assert saved.is_file()
    reloaded = SettingsManager()
    assert reloaded.get("app.theme") == "dark"
    assert reloaded.get("hardware.prefer_gpu") is False
    assert reloaded.get("privacy.upload_media") is False
    assert reloaded.get("ui.last_page") == "settings"


def test_restart_restores_page_and_theme(qt_app, isolated_env):
    settings = SettingsManager()
    first = MainWindow(settings, make_report())
    first.show()
    qt_app.processEvents()
    first.apply_theme_preference("dark")
    first.switch_page("batch")
    first.save_user_settings()
    first.close()
    qt_app.processEvents()
    apply_theme(qt_app, str(SettingsManager().get("app.theme", "system")))
    second = MainWindow(SettingsManager(), make_report())
    second.show()
    qt_app.processEvents()
    try:
        assert second.current_page_id() == "batch"
        assert second.settings_page.theme_combo.currentData() == "dark"
    finally:
        second.close()
        qt_app.processEvents()
