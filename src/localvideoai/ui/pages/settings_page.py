from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from localvideoai.ui import strings
from localvideoai.ui.theme import section_label


def _path_row(edit: QLineEdit, button: QPushButton) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(edit, 1)
    layout.addWidget(button)
    return row


class SettingsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(8)
        title = QLabel("设置")
        title.setObjectName("iosLargeTitle")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(0, 4, 8, 12)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("themeCombo")
        self.theme_combo.addItem(strings.THEME_SYSTEM, "system")
        self.theme_combo.addItem(strings.THEME_LIGHT, "light")
        self.theme_combo.addItem(strings.THEME_DARK, "dark")
        self.language_label = QLabel("简体中文（本阶段仅中文界面）")
        self.language_label.setObjectName("languageLabel")
        self.prefer_gpu = QCheckBox("有兼容 GPU 时优先加速")
        self.prefer_gpu.setObjectName("preferGpuCheck")
        self.hardware_cpu = QLabel("—")
        self.hardware_cpu.setObjectName("settingsCpuLabel")
        self.hardware_gpu = QLabel("—")
        self.hardware_gpu.setObjectName("settingsGpuLabel")
        self.hardware_vram = QLabel("—")
        self.hardware_vram.setObjectName("settingsVramLabel")
        self.hardware_ram = QLabel("—")
        self.hardware_ram.setObjectName("settingsRamLabel")
        self.hardware_profile = QLabel("—")
        self.hardware_profile.setObjectName("settingsProfileLabel")
        self.upload_label = QLabel("关闭（强制：默认不上传视频/音频/字幕/项目）")
        self.upload_label.setObjectName("uploadPolicyLabel")
        self.save_button = QPushButton(strings.SAVE_SETTINGS)
        self.save_button.setObjectName("saveSettingsButton")
        self.export_format = QComboBox()
        self.export_format.setObjectName("exportFormatCombo")
        self.export_format.addItem("SRT", "srt")
        self.export_format.addItem("VTT", "vtt")
        self.export_format.addItem("ASS", "ass")
        self.export_format.addItem("SSA", "ssa")
        self.export_container = QComboBox()
        self.export_container.setObjectName("exportContainerCombo")
        self.export_container.addItem("MP4", "mp4")
        self.export_container.addItem("MKV", "mkv")
        self.export_container.addItem("WebM", "webm")
        self.export_codec = QComboBox()
        self.export_codec.setObjectName("exportCodecCombo")
        self.export_codec.addItem("复制（不重编码）", "copy")
        self.export_codec.addItem("H.264", "h264")
        self.export_codec.addItem("H.265", "h265")
        self.export_burn_in = QCheckBox("导出时烧录字幕（会重新编码画面）")
        self.export_burn_in.setObjectName("exportBurnInCheck")
        self.models_dir_edit = QLineEdit()
        self.models_dir_edit.setObjectName("settingsModelsDirEdit")
        self.models_dir_edit.setReadOnly(True)
        self.models_dir_browse = QPushButton("浏览…")
        self.models_dir_browse.setObjectName("settingsModelsDirBrowse")
        self.projects_dir_edit = QLineEdit()
        self.projects_dir_edit.setObjectName("settingsProjectsDirEdit")
        self.projects_dir_edit.setReadOnly(True)
        self.projects_dir_browse = QPushButton("浏览…")
        self.projects_dir_browse.setObjectName("settingsProjectsDirBrowse")
        self.cache_dir_edit = QLineEdit()
        self.cache_dir_edit.setObjectName("settingsCacheDirEdit")
        self.cache_dir_edit.setReadOnly(True)
        self.cache_dir_browse = QPushButton("浏览…")
        self.cache_dir_browse.setObjectName("settingsCacheDirBrowse")
        self.allow_network = QCheckBox("允许检查更新时联网（默认关闭，不会上传视频或字幕）")
        self.allow_network.setObjectName("settingsAllowNetworkCheck")
        self.update_source_edit = QLineEdit()
        self.update_source_edit.setObjectName("settingsUpdateSourceEdit")
        self.update_source_edit.setPlaceholderText("本地 update-manifest.json，或勾选联网后填写 HTTPS 地址")
        self.license_status = QLabel("本机个人版（无需授权文件）")
        self.license_status.setObjectName("settingsLicenseStatus")
        self.license_status.setWordWrap(True)
        self.import_license_button = QPushButton(strings.IMPORT_LICENSE)
        self.import_license_button.setObjectName("settingsImportLicenseButton")
        self.check_update_button = QPushButton(strings.CHECK_UPDATE)
        self.check_update_button.setObjectName("settingsCheckUpdateButton")
        self.export_diag_button = QPushButton(strings.EXPORT_DIAGNOSTICS)
        self.export_diag_button.setObjectName("settingsExportDiagButton")

        form.addRow(section_label("外观"))
        form.addRow("主题", self.theme_combo)
        form.addRow("界面语言", self.language_label)
        form.addRow(section_label("本机硬件"))
        form.addRow("CPU", self.hardware_cpu)
        form.addRow("GPU", self.hardware_gpu)
        form.addRow("VRAM", self.hardware_vram)
        form.addRow("RAM", self.hardware_ram)
        form.addRow("性能档位", self.hardware_profile)
        form.addRow("加速", self.prefer_gpu)
        form.addRow("上传策略", self.upload_label)
        form.addRow(section_label("目录"))
        form.addRow("模型目录", _path_row(self.models_dir_edit, self.models_dir_browse))
        form.addRow("项目目录", _path_row(self.projects_dir_edit, self.projects_dir_browse))
        form.addRow("缓存目录", _path_row(self.cache_dir_edit, self.cache_dir_browse))
        form.addRow(section_label("导出"))
        form.addRow("字幕格式", self.export_format)
        form.addRow("导出容器", self.export_container)
        form.addRow("视频编码", self.export_codec)
        form.addRow("烧录", self.export_burn_in)
        form.addRow(section_label("更新与授权"))
        form.addRow("联网策略", self.allow_network)
        form.addRow("更新源", self.update_source_edit)
        form.addRow("授权状态", self.license_status)
        form.addRow(_path_row(self.import_license_button, self.check_update_button))
        form.addRow(self.export_diag_button)
        form.addRow(self.save_button)
        note = QLabel(
            "主题、设备偏好、独立模型目录和导出设置会写入本地 settings.json，并随 .vtproj 一起保存。"
            "窗口几何在关闭时自动保存。CPU / GPU / VRAM / RAM 来自本机检测，低配置走 CPU 基础功能，高配置自动使用 GPU。"
            "核心功能不依赖授权文件。检查更新默认读本机清单，只有你勾选联网并手动点检查时才会访问网络。"
        )
        note.setWordWrap(True)
        note.setObjectName("settingsFootnote")
        form.addRow(note)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    def set_hardware(self, cpu: str, gpu: str, vram: str, ram: str, profile: str) -> None:
        self.hardware_cpu.setText(cpu)
        self.hardware_gpu.setText(gpu)
        self.hardware_vram.setText(vram)
        self.hardware_ram.setText(ram)
        self.hardware_profile.setText(profile)
