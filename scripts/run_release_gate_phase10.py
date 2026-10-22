"""Phase 10 Release Gate: realtime pipeline, Chinese path, exceptions, previous editor, honest locks."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def main() -> int:
    from localvideoai.app import create_application
    from localvideoai.core.exceptions import MediaError, SubtitleError
    from localvideoai.core.paths import install_root
    from localvideoai.core.types import SubtitleSegment
    from localvideoai.engines import create_speech_engine, create_translation_engine
    from localvideoai.managers.settings_manager import SettingsManager
    from localvideoai.media.media_analyzer import MediaAnalyzer
    from localvideoai.realtime.extract import extract_pcm_window
    from localvideoai.realtime.pipeline import process_realtime_window
    from localvideoai.realtime.policy import DELAY_OPTIONS_MS, adjust_window_ms
    from localvideoai.subtitles.document import SubtitleDocument
    from localvideoai.subtitles.io import load_subtitle, save_subtitle
    from localvideoai.subtitles.sidecar import sidecar_path
    from localvideoai.ui.availability import phase_lock_reason
    from localvideoai.ui.main_window import MainWindow
    from localvideoai.ui.theme import apply_theme
    from tests.conftest import make_report

    failures: list[str] = []
    notes: dict[str, str] = {}
    data = Path(tempfile.mkdtemp(prefix="lvai_gate10_"))
    os.environ["LOCALVIDEOAI_DATA_DIR"] = str(data / "data")
    os.environ["LOCALVIDEOAI_LOG_DIR"] = str(data / "logs")
    os.environ["LOCALVIDEOAI_CONFIG_PATH"] = str(data / "settings.json")

    if DELAY_OPTIONS_MS != (1000, 3000, 5000, 10000, 30000):
        failures.append(f"delay options changed: {DELAY_OPTIONS_MS}")
    notes["adjust_accurate_1s"] = str(adjust_window_ms(1000, "accurate"))
    notes["adjust_low_30s"] = str(adjust_window_ms(30000, "low"))
    notes["adjust_slow"] = str(adjust_window_ms(3000, "balanced", 8000))
    if adjust_window_ms(1000, "accurate") != 3000:
        failures.append("accurate profile did not raise 1s to 3s")
    if adjust_window_ms(30000, "low") != 5000:
        failures.append("low profile did not cap 30s to 5s")
    if adjust_window_ms(3000, "balanced", 8000) < 8000:
        failures.append("slow job did not grow window")

    chinese_video = install_root() / "test_assets" / "videos" / "中文路径" / "10秒_测试.mp4"
    chunk = extract_pcm_window(chinese_video, 0, 1200)
    notes["chinese_pcm"] = str(len(chunk.pcm_s16le))
    if "中文路径" not in str(chinese_video) or len(chunk.pcm_s16le) < 500:
        failures.append("chinese path audio window failed")

    empty_media = data / "中文路径_门禁" / "空视频.mp4"
    empty_media.parent.mkdir(parents=True)
    empty_media.write_bytes(b"")
    try:
        MediaAnalyzer().analyze(empty_media)
        failures.append("empty media did not raise")
    except MediaError as exc:
        notes["empty_media"] = str(exc)
        if "空" not in str(exc):
            failures.append("empty media error unexpected")

    empty_srt = empty_media.with_suffix(".srt")
    empty_srt.write_bytes(b"")
    try:
        load_subtitle(empty_srt)
        failures.append("empty srt did not raise")
    except SubtitleError as exc:
        notes["empty_srt"] = str(exc)
    try:
        load_subtitle(empty_media.parent / "不存在.srt")
        failures.append("missing srt did not raise")
    except SubtitleError as exc:
        notes["missing_srt"] = str(exc)

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
    saved = save_subtitle(document, empty_media.parent / "编辑字幕.srt", "srt")
    reopened = load_subtitle(saved)
    if not sidecar_path(saved).is_file() or not reopened.segments[0].locked:
        failures.append("phase9 sidecar chinese roundtrip failed")

    speech = install_root() / "test_assets" / "audio" / "phase6" / "zh_normal.wav"
    cue = process_realtime_window(
        speech,
        0,
        3000,
        speech_engine=create_speech_engine(make_report()),
        translation_engine=create_translation_engine(make_report()),
        source_lang="zh",
        target_lang="en",
        profile="fast",
        device_preference="cpu",
        prefer_gpu=False,
    )
    notes["realtime_source"] = cue.source_text
    notes["realtime_translated"] = cue.translated_text
    notes["realtime_device"] = cue.speech_device
    notes["realtime_process_ms"] = str(cue.process_ms)
    if not cue.source_text.strip() or not cue.translated_text.strip():
        failures.append("realtime pipeline produced empty text")
    if cue.translated_text.strip() == cue.source_text.strip():
        failures.append("realtime translation was identity")
    if cue.speech_device != "cpu":
        failures.append(f"cpu request used {cue.speech_device}")

    app = create_application(["localvideoai-gate10"])
    apply_theme(app, "light")
    window = MainWindow(SettingsManager(), make_report())
    window.show()
    app.processEvents()
    notes["title"] = window.windowTitle()
    notes["menus"] = ",".join(window.menu_titles())
    if window.menu_titles() != ["文件", "编辑", "项目", "工具", "AI", "设置", "帮助"]:
        failures.append(f"unexpected menus: {window.menu_titles()}")
    if expected_lock := "不是假功能":
        if expected_lock not in window.batch_page.start_button.toolTip() or window.batch_page.start_button.isEnabled():
            failures.append("batch start not honestly locked")
        if expected_lock not in window.models_page.download_button.toolTip() or window.models_page.download_button.isEnabled():
            failures.append("download not honestly locked")
    if not window.side_panel.realtime_button.isEnabled():
        failures.append("realtime button disabled")
    delays = [window.side_panel.realtime_delay_combo.itemData(i) for i in range(window.side_panel.realtime_delay_combo.count())]
    if delays != [1000, 3000, 5000, 10000, 30000]:
        failures.append(f"delay combo {delays}")
    notes["lock_reason_sample"] = phase_lock_reason("模型下载", "后续模型管理阶段")

    window.add_subtitle_path(saved)
    app.processEvents()
    if window.subtitle_page.table.rowCount() != 1:
        failures.append("editor did not load chinese subtitle")
    window.add_video_path(chinese_video)
    app.processEvents()
    if "中文路径" not in str(window.playback.source_path or ""):
        failures.append("did not open chinese path video")
    notes["video_chinese"] = str(window.playback.source_path)

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
