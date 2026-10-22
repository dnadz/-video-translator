"""Phase 9 Release Gate: Chinese path, exceptions, editor UI, waveform, honest locks."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from localvideoai.app import create_application
    from localvideoai.core.exceptions import SubtitleError
    from localvideoai.core.paths import install_root
    from localvideoai.core.types import SubtitleSegment, TranslationRequest
    from localvideoai.engines.ctranslate2_translation_engine import CTranslate2TranslationEngine
    from localvideoai.hardware.hardware_manager import HardwareManager
    from localvideoai.managers.settings_manager import SettingsManager
    from localvideoai.media.waveform import extract_waveform_peaks
    from localvideoai.subtitles.document import SubtitleDocument
    from localvideoai.subtitles.io import load_subtitle, save_subtitle
    from localvideoai.subtitles.sidecar import sidecar_path
    from localvideoai.ui.availability import phase_lock_reason
    from localvideoai.ui.main_window import MainWindow
    from localvideoai.ui.theme import apply_theme
    from tests.conftest import make_report

    failures: list[str] = []
    notes: dict[str, str] = {}
    data = Path(tempfile.mkdtemp(prefix="lvai_gate09_"))
    os.environ["LOCALVIDEOAI_DATA_DIR"] = str(data / "data")
    os.environ["LOCALVIDEOAI_LOG_DIR"] = str(data / "logs")
    os.environ["LOCALVIDEOAI_CONFIG_PATH"] = str(data / "settings.json")

    chinese_dir = data / "中文路径_门禁"
    chinese_dir.mkdir(parents=True)

    document = SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=1234,
                end_time=4321,
                source_text="原文中文",
                corrected_text="校正中文",
                translated_text="English line",
                locked=True,
            )
        ],
        format_name="srt",
    )
    saved = save_subtitle(document, chinese_dir / "编辑字幕.srt", "srt")
    if "中文路径" not in str(saved):
        failures.append("chinese save path missing 中文路径")
    if not sidecar_path(saved).is_file():
        failures.append("sidecar missing after chinese save")
    reopened = load_subtitle(saved)
    if reopened.segments[0].start_time != 1234 or not reopened.segments[0].locked:
        failures.append("chinese path sidecar roundtrip failed")
    notes["chinese_sidecar"] = str(sidecar_path(saved))

    empty = chinese_dir / "空文件.srt"
    empty.write_bytes(b"")
    try:
        load_subtitle(empty)
        failures.append("empty srt did not raise")
    except SubtitleError as exc:
        notes["empty_error"] = str(exc)
        if "空" not in str(exc):
            failures.append("empty error text unexpected")
    try:
        load_subtitle(chinese_dir / "不存在.srt")
        failures.append("missing srt did not raise")
    except SubtitleError as exc:
        notes["missing_error"] = str(exc)

    abnormal = install_root() / "test_assets" / "subtitles" / "异常字幕.srt"
    if abnormal.is_file():
        parsed = load_subtitle(abnormal)
        notes["abnormal_warnings"] = str(len(parsed.warnings))
        if not parsed.warnings:
            failures.append("abnormal srt produced no warnings")
    else:
        failures.append("missing 异常字幕.srt")

    video = install_root() / "test_assets" / "videos" / "中文路径" / "10秒_测试.mp4"
    peaks = extract_waveform_peaks(video, hop_ms=20)
    notes["waveform_peaks"] = str(len(peaks.peaks))
    notes["waveform_duration"] = str(peaks.duration_ms)
    if peaks.duration_ms < 9000 or not peaks.peaks:
        failures.append("waveform from chinese path video failed")

    engine = CTranslate2TranslationEngine(make_report())
    translated = engine.translate(
        TranslationRequest("The weather is nice today.", "en", "zh", device_preference="cpu")
    )
    notes["translation"] = translated.text
    if not translated.text.strip() or translated.text.strip() == "The weather is nice today.":
        failures.append("core translation produced empty or identity text")

    app = QApplication.instance() or create_application(["localvideoai-gate09"])
    apply_theme(app, "light")
    window = MainWindow(SettingsManager(), HardwareManager().detect())
    window.show()
    app.processEvents()
    notes["title"] = window.windowTitle()
    notes["menus"] = ",".join(window.menu_titles())
    if window.menu_titles() != ["文件", "编辑", "项目", "工具", "AI", "设置", "帮助"]:
        failures.append(f"unexpected menus: {window.menu_titles()}")

    batch_tip = window.batch_page.start_button.toolTip()
    download_tip = window.models_page.download_button.toolTip()
    expected_lock = "不是假功能"
    if expected_lock not in batch_tip or window.batch_page.start_button.isEnabled():
        failures.append(f"batch start not honestly locked: {batch_tip}")
    if expected_lock not in download_tip or window.models_page.download_button.isEnabled():
        failures.append(f"download not honestly locked: {download_tip}")
    if not window.side_panel.translate_button.isEnabled():
        failures.append("translate button disabled")
    if not window.subtitle_page.add_button.isEnabled():
        failures.append("add cue button disabled")
    notes["lock_reason_sample"] = phase_lock_reason("模型下载", "后续模型管理阶段")

    window.add_subtitle_path(saved)
    app.processEvents()
    page = window.subtitle_page
    if page.table.rowCount() != 1:
        failures.append(f"ui did not load chinese subtitle rows={page.table.rowCount()}")
    page.add_cue(8000, "新增中文")
    app.processEvents()
    if page.table.rowCount() != 2:
        failures.append("add_cue failed")
    page.table.selectRow(1)
    page.split_selected()
    app.processEvents()
    if page.table.rowCount() != 3:
        failures.append("split_selected failed")
    page.undo()
    app.processEvents()
    if page.table.rowCount() != 2:
        failures.append("undo after split failed")
    window.save_subtitle()
    app.processEvents()
    window.subtitle_page.clear()
    app.processEvents()
    window.add_subtitle_path(saved)
    app.processEvents()
    if page.table.rowCount() != 2:
        failures.append("save/reopen via UI lost added cue")
    first = page.document.segments[0]
    if not first.locked or first.corrected_text != "校正中文":
        failures.append("UI reopen lost lock or corrected text")

    window.add_subtitle_path(empty)
    app.processEvents()
    notes["empty_ui_status"] = window.statusBar().currentMessage()
    if "空" not in (window.statusBar().currentMessage() or ""):
        failures.append("empty file UI did not show error")

    window.add_video_path(video)
    app.processEvents()
    notes["video_chinese"] = str(window.playback.source_path)
    if "中文路径" not in str(window.playback.source_path or ""):
        failures.append("did not open chinese path video")

    window.close()
    app.processEvents()

    print("NOTES", notes)
    if failures:
        print("FAILURES")
        for item in failures:
            print("-", item)
        return 1
    print("GATE_SCRIPT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
