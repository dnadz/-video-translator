from localvideoai.ui.theme import LIGHT, apply_theme, build_stylesheet, pick_ui_font_family, tokens_for


def test_ios_light_theme_uses_system_blue(qt_app):
    resolved = apply_theme(qt_app, "light")
    assert resolved == "light"
    sheet = qt_app.styleSheet()
    assert LIGHT.tint == "#007AFF"
    assert "#007AFF" in sheet
    assert "#F2F2F7" in sheet
    assert "border-radius: 10px" in sheet
    assert "QToolBar#pageToolBar" in sheet
    assert pick_ui_font_family() in sheet


def test_ios_dark_theme_uses_system_blue(qt_app):
    resolved = apply_theme(qt_app, "dark")
    assert resolved == "dark"
    tokens = tokens_for("dark")
    assert tokens.tint == "#0A84FF"
    assert tokens.surface == "#1C1C1E"
    sheet = qt_app.styleSheet()
    assert "#0A84FF" in sheet
    assert "#1C1C1E" in sheet
    apply_theme(qt_app, "light")


def test_ios_stylesheet_covers_primary_and_destructive_actions():
    sheet = build_stylesheet(LIGHT, "Microsoft YaHei UI")
    for name in (
        "startTranslateButton",
        "startTranscribeButton",
        "saveSettingsButton",
        "batchStartButton",
        "playButton",
        "batchCancelButton",
        "deleteModelButton",
    ):
        assert name in sheet


def test_settings_page_keeps_controls_and_adds_large_title(main_window):
    page = main_window.settings_page
    assert page.objectName() == "settingsPage"
    assert page.theme_combo.objectName() == "themeCombo"
    assert page.save_button.objectName() == "saveSettingsButton"
    from PySide6.QtWidgets import QLabel

    headers = [label.text() for label in page.findChildren(QLabel) if label.objectName() == "iosLargeTitle"]
    assert headers == ["设置"]
    sections = [label.text() for label in page.findChildren(QLabel) if label.objectName() == "iosSectionHeader"]
    assert "外观" in sections
    assert "导出" in sections
