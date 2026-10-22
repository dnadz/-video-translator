from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_SYSTEM = "system"


@dataclass(frozen=True)
class IOSTokens:
    """Apple HIG system colors, mapped for Qt Fusion + QSS."""

    grouped: str
    surface: str
    elevated: str
    fill: str
    fill_strong: str
    label: str
    secondary: str
    tertiary: str
    separator: str
    tint: str
    tint_pressed: str
    tint_soft: str
    destructive: str
    destructive_pressed: str
    green: str
    stage: str
    overlay: str
    on_tint: str


LIGHT = IOSTokens(
    grouped="#F2F2F7",
    surface="#FFFFFF",
    elevated="#FFFFFF",
    fill="#E5E5EA",
    fill_strong="#D1D1D6",
    label="#000000",
    secondary="#6C6C70",
    tertiary="#8E8E93",
    separator="#C6C6C8",
    tint="#007AFF",
    tint_pressed="#0063D1",
    tint_soft="#D6E9FF",
    destructive="#FF3B30",
    destructive_pressed="#D70015",
    green="#34C759",
    stage="#000000",
    overlay="rgba(0, 0, 0, 168)",
    on_tint="#FFFFFF",
)

DARK = IOSTokens(
    grouped="#000000",
    surface="#1C1C1E",
    elevated="#2C2C2E",
    fill="#3A3A3C",
    fill_strong="#48484A",
    label="#FFFFFF",
    secondary="#EBEBF5",
    tertiary="#8E8E93",
    separator="#38383A",
    tint="#0A84FF",
    tint_pressed="#409CFF",
    tint_soft="#0A3180",
    destructive="#FF453A",
    destructive_pressed="#FF6961",
    green="#30D158",
    stage="#000000",
    overlay="rgba(0, 0, 0, 180)",
    on_tint="#FFFFFF",
)


def resolve_theme(preference: str) -> str:
    if preference == THEME_DARK:
        return THEME_DARK
    if preference == THEME_LIGHT:
        return THEME_LIGHT
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return THEME_DARK
    return THEME_LIGHT


def pick_ui_font_family() -> str:
    fonts_dir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    if (fonts_dir / "msyh.ttc").is_file() or (fonts_dir / "msyh.ttf").is_file():
        return "Microsoft YaHei UI"
    families = set(QFontDatabase.families())
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "SimHei"):
        if name in families:
            return name
    return QGuiApplication.font().family() or "Sans Serif"


def tokens_for(resolved: str) -> IOSTokens:
    return DARK if resolved == THEME_DARK else LIGHT


def _palette(tokens: IOSTokens) -> QPalette:
    palette = QPalette()
    window = QColor(tokens.grouped)
    text = QColor(tokens.label)
    base = QColor(tokens.surface)
    button = QColor(tokens.fill)
    highlight = QColor(tokens.tint)
    placeholder = QColor(tokens.tertiary)
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens.elevated))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, button)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens.on_tint))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(tokens.elevated))
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, placeholder)
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(tokens.destructive))
    return palette


def build_stylesheet(tokens: IOSTokens, family: str) -> str:
    t = tokens
    return f"""
        QWidget {{
            font-family: "{family}";
            font-size: 10pt;
            color: {t.label};
        }}
        QMainWindow, QDialog, QMessageBox {{
            background: {t.grouped};
        }}
        QMenuBar {{
            background: {t.grouped};
            color: {t.label};
            padding: 4px 10px 0 10px;
            border: none;
        }}
        QMenuBar::item {{
            background: transparent;
            padding: 6px 10px;
            border-radius: 8px;
        }}
        QMenuBar::item:selected {{
            background: {t.fill};
        }}
        QMenu {{
            background: {t.surface};
            color: {t.label};
            border: 1px solid {t.separator};
            border-radius: 12px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 8px 18px;
            border-radius: 8px;
        }}
        QMenu::item:selected {{
            background: {t.tint};
            color: {t.on_tint};
        }}
        QMenu::separator {{
            height: 1px;
            background: {t.separator};
            margin: 6px 10px;
        }}
        QToolBar#pageToolBar {{
            background: {t.fill};
            border: none;
            border-radius: 12px;
            spacing: 2px;
            padding: 3px;
            margin: 8px 12px 6px 12px;
        }}
        QToolBar#pageToolBar QToolButton {{
            background: transparent;
            color: {t.label};
            border: none;
            border-radius: 9px;
            padding: 7px 16px;
            min-height: 28px;
        }}
        QToolBar#pageToolBar QToolButton:hover {{
            background: {t.fill_strong};
        }}
        QToolBar#pageToolBar QToolButton:checked {{
            background: {t.surface};
            color: {t.label};
            font-weight: 600;
        }}
        QStatusBar {{
            background: {t.grouped};
            color: {t.secondary};
            border-top: 1px solid {t.separator};
            min-height: 26px;
            padding: 2px 10px;
        }}
        QSplitter::handle {{
            background: {t.separator};
            width: 1px;
            height: 1px;
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 4px 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {t.fill_strong};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 8px;
            margin: 2px 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: {t.fill_strong};
            border-radius: 4px;
            min-width: 24px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
            width: 0;
        }}
        QPushButton {{
            background: {t.fill};
            color: {t.label};
            border: none;
            border-radius: 10px;
            padding: 7px 14px;
            min-height: 30px;
        }}
        QPushButton:hover {{
            background: {t.fill_strong};
        }}
        QPushButton:pressed {{
            background: {t.fill_strong};
            padding-top: 8px;
        }}
        QPushButton:disabled {{
            color: {t.tertiary};
            background: {t.fill};
        }}
        QPushButton:checked {{
            background: {t.tint_soft};
            color: {t.tint};
            font-weight: 600;
        }}
        QPushButton#startTranslateButton,
        QPushButton#startTranscribeButton,
        QPushButton#startOcrButton,
        QPushButton#startRealtimeButton,
        QPushButton#saveSettingsButton,
        QPushButton#batchStartButton,
        QPushButton#downloadModelButton,
        QPushButton#playButton {{
            background: {t.tint};
            color: {t.on_tint};
            font-weight: 600;
        }}
        QPushButton#startTranslateButton:hover,
        QPushButton#startTranscribeButton:hover,
        QPushButton#startOcrButton:hover,
        QPushButton#startRealtimeButton:hover,
        QPushButton#saveSettingsButton:hover,
        QPushButton#batchStartButton:hover,
        QPushButton#downloadModelButton:hover,
        QPushButton#playButton:hover {{
            background: {t.tint_pressed};
        }}
        QPushButton#startTranslateButton:disabled,
        QPushButton#startTranscribeButton:disabled,
        QPushButton#startOcrButton:disabled,
        QPushButton#startRealtimeButton:disabled,
        QPushButton#saveSettingsButton:disabled,
        QPushButton#batchStartButton:disabled,
        QPushButton#downloadModelButton:disabled,
        QPushButton#playButton:disabled {{
            background: {t.fill};
            color: {t.tertiary};
        }}
        QPushButton#batchCancelButton,
        QPushButton#deleteModelButton,
        QPushButton#batchRemoveButton {{
            background: transparent;
            color: {t.destructive};
            font-weight: 600;
        }}
        QPushButton#batchCancelButton:hover,
        QPushButton#deleteModelButton:hover,
        QPushButton#batchRemoveButton:hover {{
            background: {t.fill};
        }}
        QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background: {t.surface};
            color: {t.label};
            border: 1px solid {t.separator};
            border-radius: 10px;
            padding: 6px 10px;
            selection-background-color: {t.tint};
            selection-color: {t.on_tint};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background: {t.surface};
            border: 1px solid {t.separator};
            border-radius: 10px;
            selection-background-color: {t.tint};
            selection-color: {t.on_tint};
            padding: 4px;
        }}
        QListWidget, QTableWidget, QTreeView {{
            background: {t.surface};
            border: none;
            border-radius: 12px;
            outline: none;
            alternate-background-color: {t.grouped};
        }}
        QListWidget::item, QTableWidget::item {{
            padding: 8px 12px;
            min-height: 28px;
        }}
        QListWidget::item:selected, QTableWidget::item:selected {{
            background: {t.tint};
            color: {t.on_tint};
            border-radius: 8px;
        }}
        QHeaderView::section {{
            background: {t.surface};
            color: {t.secondary};
            border: none;
            border-bottom: 1px solid {t.separator};
            padding: 8px 10px;
            font-weight: 600;
        }}
        QTabWidget::pane {{
            border: none;
            background: transparent;
            top: 4px;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {t.secondary};
            padding: 8px 14px;
            margin-right: 2px;
            border: none;
            border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:selected {{
            color: {t.tint};
            font-weight: 600;
            border-bottom: 2px solid {t.tint};
        }}
        QTabBar::tab:hover {{
            color: {t.label};
        }}
        QGroupBox {{
            font-weight: 600;
            color: {t.secondary};
            border: none;
            margin-top: 16px;
            padding-top: 8px;
        }}
        QCheckBox, QRadioButton {{
            spacing: 8px;
            color: {t.label};
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 20px;
            height: 20px;
            border-radius: 6px;
            border: 1px solid {t.separator};
            background: {t.surface};
        }}
        QCheckBox::indicator:checked {{
            background: {t.tint};
            border: 1px solid {t.tint};
        }}
        QRadioButton::indicator {{
            border-radius: 10px;
        }}
        QRadioButton::indicator:checked {{
            background: {t.tint};
            border: 1px solid {t.tint};
        }}
        QSlider::groove:horizontal {{
            background: {t.fill};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {t.tint};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {t.surface};
            border: 1px solid {t.separator};
            width: 18px;
            height: 18px;
            margin: -8px 0;
            border-radius: 9px;
        }}
        QProgressBar {{
            background: {t.fill};
            border: none;
            border-radius: 6px;
            text-align: center;
            color: {t.secondary};
            min-height: 8px;
        }}
        QProgressBar::chunk {{
            background: {t.tint};
            border-radius: 6px;
        }}
        QToolTip {{
            background: {t.elevated};
            color: {t.label};
            border: 1px solid {t.separator};
            border-radius: 8px;
            padding: 6px 8px;
        }}
        #projectListPanel, #sidePanel {{
            background: {t.grouped};
        }}
        #projectMediaList, #subtitleInfo {{
            background: {t.surface};
        }}
        #videoStage {{
            background: {t.stage};
            border: none;
            border-radius: 14px;
        }}
        #videoStageTitle {{
            font-size: 20px;
            font-weight: 600;
            color: {t.on_tint};
        }}
        #videoStageHint, #videoStagePath {{
            color: {t.tertiary};
        }}
        #timelinePanel {{
            background: {t.grouped};
            border-top: 1px solid {t.separator};
        }}
        #timelineCaption, #iosSectionHeader, #iosLargeTitle {{
            color: {t.label};
            font-weight: 700;
        }}
        #iosLargeTitle {{
            font-size: 22px;
        }}
        #iosSectionHeader {{
            font-size: 12px;
            color: {t.secondary};
            font-weight: 600;
            padding-top: 10px;
        }}
        #workspaceHint, #modelsHint, #batchHint, #timelineHint, #subtitleHint,
        #hardwareInfoLabel, #translationContextHint, #realtimeActualLabel,
        #settingsFootnote, #sidePrivacyHint, #modelsEmptyLabel, #modelsRecommendLabel {{
            color: {t.secondary};
        }}
        #realtimeCaption, #realtimeCaptionBar, #realtimeFullscreenCaption {{
            color: {t.on_tint};
            background: {t.overlay};
            border-radius: 10px;
            padding: 8px 14px;
            font-size: 16px;
        }}
        QLabel#hardwareStatusLabel {{
            color: {t.tertiary};
        }}
        QDialogButtonBox QPushButton {{
            min-width: 88px;
        }}
        QDialogButtonBox QPushButton[text="OK"],
        QDialogButtonBox QPushButton[text="确定"] {{
            background: {t.tint};
            color: {t.on_tint};
            font-weight: 600;
        }}
    """


def section_label(text: str):
    from PySide6.QtWidgets import QLabel

    label = QLabel(text)
    label.setObjectName("iosSectionHeader")
    return label


def apply_theme(app: QApplication, preference: str) -> str:
    """Apply iOS-inspired Fusion palette + QSS. Returns the resolved light/dark value."""
    resolved = resolve_theme(preference)
    tokens = tokens_for(resolved)
    app.setStyle("Fusion")
    family = pick_ui_font_family()
    app.setFont(QFont(family, 10))
    app.setPalette(_palette(tokens))
    app.setStyleSheet(build_stylesheet(tokens, family))
    return resolved
