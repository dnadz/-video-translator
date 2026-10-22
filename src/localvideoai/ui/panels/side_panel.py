from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localvideoai.translation.context import context_hint_for
from localvideoai.ui import strings
from localvideoai.ui.availability import unlock_widget
from localvideoai.ui.panels.media_info_panel import MediaInfoPanel
from localvideoai.ui.theme import section_label


class SidePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidePanel")
        self.setMinimumWidth(240)
        self._external_lines: list[str] = []
        self._embedded_lines: list[str] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel(strings.SIDE_HINT)
        title.setObjectName("iosSectionHeader")
        title.setWordWrap(True)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("sideTabs")
        self.media_info = MediaInfoPanel()
        self.tabs.addTab(self.media_info, "媒体")
        self.tabs.addTab(self._build_subtitle_tab(), "字幕")
        self.tabs.addTab(self._build_ai_tab(), "AI设置")
        layout.addWidget(title)
        layout.addWidget(self.tabs, 1)

    def _build_subtitle_tab(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        self.subtitle_info = QTextEdit()
        self.subtitle_info.setObjectName("subtitleInfo")
        self.subtitle_info.setReadOnly(True)
        self.subtitle_info.setPlainText("尚未打开视频。打开后会列出内嵌字幕轨道；外挂字幕也会显示在这里。")
        box.addWidget(self.subtitle_info)
        return page

    def _build_ai_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(4, 4, 8, 12)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.hardware_label = QLabel("CPU：—\nGPU：—\nVRAM：—\nRAM：—")
        self.hardware_label.setObjectName("hardwareInfoLabel")
        self.hardware_label.setWordWrap(True)
        self.device_combo = QComboBox()
        self.device_combo.setObjectName("deviceCombo")
        self.device_combo.addItem(strings.DEVICE_AUTO, "auto")
        self.device_combo.addItem(strings.DEVICE_CPU, "cpu")
        self.device_combo.addItem(strings.DEVICE_GPU, "gpu")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("targetLanguageCombo")
        self.language_combo.addItem("中文（简体）", "zh-CN")
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("日本語", "ja")
        self.source_language_combo = QComboBox()
        self.source_language_combo.setObjectName("sourceLanguageCombo")
        self.source_language_combo.addItem("自动检测", "auto")
        self.source_language_combo.addItem("中文", "zh")
        self.source_language_combo.addItem("英文", "en")
        self.source_language_combo.addItem("日文", "ja")
        self.translate_button = QPushButton(strings.START_TRANSLATE)
        self.translate_button.setObjectName("startTranslateButton")
        unlock_widget(self.translate_button, "使用本机 CTranslate2 目录模型翻译当前字幕。不会上传。")
        self.transcribe_button = QPushButton(strings.START_TRANSCRIBE)
        self.transcribe_button.setObjectName("startTranscribeButton")
        unlock_widget(self.transcribe_button, "使用本机 faster-whisper 识别当前视频音轨。不会上传。")
        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("translationQualityCombo")
        self.quality_combo.addItem(strings.QUALITY_FAST, "fast")
        self.quality_combo.addItem(strings.QUALITY_STANDARD, "standard")
        self.quality_combo.addItem(strings.QUALITY_HIGH, "high")
        self.quality_combo.setCurrentIndex(1)
        self.context_hint = QLabel(context_hint_for("standard"))
        self.context_hint.setObjectName("translationContextHint")
        self.context_hint.setWordWrap(True)
        self.quality_combo.currentIndexChanged.connect(self._update_context_hint)
        self.extra_zh = QCheckBox("同时译成中文")
        self.extra_zh.setObjectName("extraTargetZh")
        self.extra_en = QCheckBox("同时译成英文")
        self.extra_en.setObjectName("extraTargetEn")
        self.extra_ja = QCheckBox("同时译成日文")
        self.extra_ja.setObjectName("extraTargetJa")
        self.resources_button = QPushButton(strings.EDIT_TRANSLATION_RESOURCES)
        self.resources_button.setObjectName("editTranslationResourcesButton")
        unlock_widget(self.resources_button, "编辑本机术语表、翻译记忆和人名字典。用户修改优先。")
        self.ocr_region_combo = QComboBox()
        self.ocr_region_combo.setObjectName("ocrRegionCombo")
        self.ocr_region_combo.addItem("自动检测字幕区域", "auto")
        self.ocr_region_combo.addItem("手动框选区域", "manual")
        self.pick_ocr_region_button = QPushButton(strings.PICK_OCR_REGION)
        self.pick_ocr_region_button.setObjectName("pickOcrRegionButton")
        unlock_widget(self.pick_ocr_region_button, "从当前视频截一帧，拖拽框选硬字幕区域。")
        self.ocr_button = QPushButton(strings.START_OCR)
        self.ocr_button.setObjectName("startOcrButton")
        unlock_widget(self.ocr_button, "使用本机 RapidOCR 识别烧录在画面上的字幕。不会上传。")
        self.diarize_button = QPushButton(strings.START_DIARIZE)
        self.diarize_button.setObjectName("startDiarizeButton")
        unlock_widget(self.diarize_button, "用本机说话人模型给当前字幕标注 Speaker 1/2/3。模型缺失时保持普通字幕。")
        self.speaker_map_button = QPushButton(strings.EDIT_SPEAKER_MAP)
        self.speaker_map_button.setObjectName("editSpeakerMapButton")
        unlock_widget(self.speaker_map_button, "把 Speaker 1 改成张三，并按人物设置字幕样式。保存在 sidecar。")
        self.quality_button = QPushButton(strings.START_QUALITY_CHECK)
        self.quality_button.setObjectName("startQualityButton")
        unlock_widget(self.quality_button, "对本机字幕做纠错、翻译审核和 QA。规则评分，不是随机数。")
        self.quality_filter_box = QCheckBox(strings.FILTER_BELOW_90)
        self.quality_filter_box.setObjectName("qualityBelow90SideFilter")
        self.quality_jump_button = QPushButton(strings.JUMP_QUALITY_ISSUE)
        self.quality_jump_button.setObjectName("jumpQualityIssueButton")
        unlock_widget(self.quality_jump_button, "跳到下一条问题字幕，并定位到对应时间。")
        self.quality_confirm_button = QPushButton(strings.CONFIRM_QUALITY)
        self.quality_confirm_button.setObjectName("confirmQualityButton")
        unlock_widget(self.quality_confirm_button, "人工确认当前字幕。确认后仍可锁定，防止 AI 覆盖。")
        self.quality_lock_button = QPushButton(strings.LOCK_CONFIRMED)
        self.quality_lock_button.setObjectName("lockConfirmedButton")
        unlock_widget(self.quality_lock_button, "把已人工确认的字幕锁定。锁定后识别/翻译不能覆盖。")
        self.hardsub_mode_combo = QComboBox()
        self.hardsub_mode_combo.setObjectName("hardSubModeCombo")
        self.hardsub_mode_combo.addItem(strings.HARDSUB_KEEP, "keep")
        self.hardsub_mode_combo.addItem(strings.HARDSUB_OVERLAY, "overlay")
        self.hardsub_mode_combo.addItem(strings.HARDSUB_SMART, "smart")
        self.hardsub_mode_combo.setCurrentIndex(2)
        self.hardsub_button = QPushButton(strings.START_HARDSUB)
        self.hardsub_button.setObjectName("startHardSubButton")
        unlock_widget(
            self.hardsub_button,
            "OCR 定位并跟踪字幕区。优先快速修复，可用时走本机图像修复；不可靠时自动建议覆盖模式。会生成真实视频。",
        )
        self.realtime_profile_combo = QComboBox()
        self.realtime_profile_combo.setObjectName("realtimeProfileCombo")
        self.realtime_profile_combo.addItem(strings.REALTIME_LOW, "low")
        self.realtime_profile_combo.addItem(strings.REALTIME_FAST, "fast")
        self.realtime_profile_combo.addItem(strings.REALTIME_BALANCED, "balanced")
        self.realtime_profile_combo.addItem(strings.REALTIME_ACCURATE, "accurate")
        self.realtime_profile_combo.setCurrentIndex(2)
        self.realtime_delay_combo = QComboBox()
        self.realtime_delay_combo.setObjectName("realtimeDelayCombo")
        for ms, label in ((1000, "1秒"), (3000, "3秒"), (5000, "5秒"), (10000, "10秒"), (30000, "30秒")):
            self.realtime_delay_combo.addItem(label, ms)
        self.realtime_delay_combo.setCurrentIndex(1)
        self.realtime_actual_label = QLabel("实际窗口：尚未开始")
        self.realtime_actual_label.setObjectName("realtimeActualLabel")
        self.realtime_actual_label.setWordWrap(True)
        self.realtime_button = QPushButton(strings.START_REALTIME)
        self.realtime_button.setObjectName("startRealtimeButton")
        unlock_widget(
            self.realtime_button,
            "播放时按窗口抽取音频，后台识别并翻译，字幕叠在画面上。不会上传。",
        )
        form.addRow(section_label("本机"))
        form.addRow("硬件", self.hardware_label)
        form.addRow("计算设备", self.device_combo)
        form.addRow(section_label("识别与翻译"))
        form.addRow("识别/源语言", self.source_language_combo)
        form.addRow("目标语言", self.language_combo)
        form.addRow("翻译质量", self.quality_combo)
        form.addRow(self.context_hint)
        form.addRow(self.extra_zh)
        form.addRow(self.extra_en)
        form.addRow(self.extra_ja)
        form.addRow(self.transcribe_button)
        form.addRow(self.ocr_button)
        form.addRow(self.translate_button)
        form.addRow(self.resources_button)
        form.addRow(section_label("实时"))
        form.addRow("实时模式", self.realtime_profile_combo)
        form.addRow("目标延迟", self.realtime_delay_combo)
        form.addRow(self.realtime_actual_label)
        form.addRow(self.realtime_button)
        form.addRow(section_label("说话人与质量"))
        form.addRow(self.diarize_button)
        form.addRow(self.speaker_map_button)
        form.addRow(self.quality_button)
        form.addRow(self.quality_filter_box)
        form.addRow(self.quality_jump_button)
        form.addRow(self.quality_confirm_button)
        form.addRow(self.quality_lock_button)
        form.addRow(section_label("硬字幕"))
        form.addRow("识别区域", self.ocr_region_combo)
        form.addRow(self.pick_ocr_region_button)
        form.addRow("处理方式", self.hardsub_mode_combo)
        form.addRow(self.hardsub_button)
        hint = QLabel("语音识别、硬字幕 OCR、翻译和实时预览都在本机运行，默认不联网。" + strings.CONTEXT_HINT)
        hint.setWordWrap(True)
        hint.setObjectName("sidePrivacyHint")
        form.addRow(hint)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        return page

    def set_hardware_text(self, text: str) -> None:
        self.hardware_label.setText(text)

    def _update_context_hint(self) -> None:
        quality = str(self.quality_combo.currentData() or "standard")
        self.context_hint.setText(context_hint_for(quality))

    def extra_target_langs(self) -> list[str]:
        primary = str(self.language_combo.currentData() or "")
        if primary.lower().startswith("zh"):
            primary = "zh"
        extras: list[str] = []
        for box, code in ((self.extra_zh, "zh"), (self.extra_en, "en"), (self.extra_ja, "ja")):
            if box.isChecked() and code != primary:
                extras.append(code)
        return extras

    def set_subtitle_summary(self, lines: list[str]) -> None:
        self._external_lines = list(lines)
        self._render_subtitle_tab()

    def set_embedded_summary(self, lines: list[str]) -> None:
        self._embedded_lines = list(lines)
        self._render_subtitle_tab()

    def _render_subtitle_tab(self) -> None:
        parts = ["【内嵌字幕】"]
        parts.extend(self._embedded_lines or ["尚未打开视频，或当前视频没有内嵌字幕。"])
        parts.extend(["", "【外挂字幕】"])
        parts.extend(self._external_lines or ["尚未添加外部字幕文件。"])
        self.subtitle_info.setPlainText("\n".join(parts))

    def show_media_tab(self) -> None:
        self.tabs.setCurrentWidget(self.media_info)
