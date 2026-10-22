from pathlib import Path

from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.ui import strings
from simplecaption.runtime import find_models_tree, prepare_runtime
from simplecaption.srtio import save_role_srt
from simplecaption.window import SimpleWindow


def test_models_tree_is_the_project_models_folder():
    found = find_models_tree()
    assert found is not None
    assert found.name == "models"
    assert (found / "speech").is_dir()
    assert (found / "translation").is_dir()


def test_prepare_runtime_keeps_existing_lookup():
    found = prepare_runtime()
    assert found is not None
    assert found.name == "models"


def test_save_translated_srt_uses_translation(tmp_path: Path):
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=0,
                end_time=1200,
                source_text="你好",
                translated_text="Hello",
            )
        ],
        format_name="srt",
        detected_language="zh",
    )
    path = save_role_srt(document, tmp_path / "demo.en.srt", "translated")
    text = path.read_text(encoding="utf-8")
    assert "Hello" in text
    assert "你好" not in text
    assert document.segments[0].source_text == "你好"
    assert document.segments[0].translated_text == "Hello"
    assert not (tmp_path / "demo.en.srt.lvai.json").exists()


def test_window_starts_with_recognize_and_translate(qt_app):
    window = SimpleWindow()
    assert window.windowTitle() == "LocalVideoAI"
    assert window.full_button.text() == "打开高级工作站…"
    assert window.transcribe_button.text() == "仅识别 / 重新识别"
    assert window.translate_button.text() == "仅翻译 / 重新翻译"
    assert window.start_button.text() == "② 开始翻译"
    assert not window.advanced_toggle.isChecked()
    assert not window.blur_checkbox.isChecked()
    assert not window.transcribe_button.isEnabled()
    assert not window.translate_button.isEnabled()
    assert window.target_combo.currentData() == "en"
    assert window.quality_combo.currentData() == "standard"
    assert "前 6 条" in window.hint.text()
    assert not window.cover_button.isEnabled()
    window.close()


def test_full_mode_opens_the_workstation(qt_app):
    from localvideoai.managers.settings_manager import SettingsManager
    from tests.conftest import make_report

    window = SimpleWindow(SettingsManager(), make_report())
    window.open_full_mode()
    assert window._full_window is not None
    assert "翻译工作站" in window._full_window.windowTitle()
    window._full_window.close()
    window.close()


def test_selecting_media_enables_only_recognize(qt_app, tmp_path: Path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"not a real video")
    window = SimpleWindow()
    window.set_media(media)
    assert window.transcribe_button.isEnabled()
    assert not window.translate_button.isEnabled()
    assert "clip.mp4" in window.drop_label.text()
    window.show_document(
        SubtitleDocument(
            segments=[SubtitleSegment(id=1, start_time=0, end_time=500, source_text="line")],
            format_name="srt",
        )
    )
    assert window.translate_button.isEnabled()
    assert window.table.rowCount() == 1
    assert window.table.item(0, 2).text() == "line"
    assert not window.cover_button.isEnabled()
    window.close()


def test_cover_mosaics_the_bottom_band(tmp_path: Path):
    import subprocess

    from localvideoai.media.ffmpeg_runtime import find_ffmpeg
    from simplecaption.cover import cover_burned_subtitles

    ffmpeg = find_ffmpeg()
    video = tmp_path / "clip.mp4"
    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=10:duration=1",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    srt = tmp_path / "clip.ja.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nこんにちは\n", encoding="utf-8")
    output = cover_burned_subtitles(video, srt, tmp_path / "clip.blur.mp4")
    assert output.is_file()
    assert output.stat().st_size > 1000
    before = _rgb_frame(ffmpeg, video)
    after = _rgb_frame(ffmpeg, output)
    top_before, top_after = before[:70], after[:70]
    bottom_before, bottom_after = before[145:], after[145:]
    top_delta = _mean_abs(top_before, top_after)
    bottom_delta = _mean_abs(bottom_before, bottom_after)
    assert bottom_delta > top_delta


def _rgb_frame(ffmpeg: Path, video: Path):
    import subprocess

    completed = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _mean_abs(left: bytes, right: bytes) -> float:
    count = min(len(left), len(right))
    if count == 0:
        return 0.0
    return sum(abs(left[index] - right[index]) for index in range(count)) / count
