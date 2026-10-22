from __future__ import annotations

from pathlib import Path

import pytest

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.paths import install_root
from localvideoai.core.types import SubtitleSegment
from localvideoai.engines.file_subtitle_engine import FileSubtitleEngine
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import load_subtitle, save_subtitle
from localvideoai.subtitles.timecodes import parse_timestamp


def _assets() -> Path:
    return install_root() / "test_assets" / "subtitles"


def test_subtitle_segment_fields_exist():
    segment = SubtitleSegment(
        id=1,
        start_time=1000,
        end_time=2000,
        speaker="A",
        source_text="src",
        corrected_text="fix",
        translated_text="译",
        language="zh",
        confidence=0.9,
        locked=True,
        style_id="Default",
    )
    assert segment.display_text() == "fix"
    cue = segment.to_cue()
    assert cue.start_ms == 1000
    assert cue.text == "fix"


def test_multilingual_roundtrip_all_formats():
    engine = FileSubtitleEngine()
    source = engine.load_document(_assets() / "多语言.srt")
    assert len(source.segments) == 5
    texts = [item.source_text for item in source.segments]
    assert "你好，世界。" in texts
    assert "Hello, world!" in texts
    assert "こんにちは、世界。" in texts
    assert "这是双语\nThis is bilingual" in texts
    assert "♪" in texts[-1]
    speakers = ["旁白", "Host", "案内", "", ""]
    for fmt in ("srt", "vtt", "ass", "ssa"):
        loaded = engine.load_document(_assets() / f"多语言.{fmt}")
        assert [item.source_text.replace("\\N", "\n") for item in loaded.segments] == texts
        if fmt in {"vtt", "ass", "ssa"}:
            assert [item.speaker for item in loaded.segments] == speakers


def test_chinese_path_import():
    document = load_subtitle(_assets() / "中文路径" / "中文字幕.srt")
    assert "中文路径" in str(document.source_path)
    assert document.segments[0].source_text.startswith("你好")


def test_thousand_cues_sort_save_reopen(tmp_path):
    original = load_subtitle(_assets() / "一千条.srt")
    assert len(original.segments) == 1000
    starts = [item.start_time for item in original.segments]
    assert starts == sorted(starts)
    shuffled = list(reversed(original.segments))
    for index, segment in enumerate(shuffled):
        segment.id = index
    messy = SubtitleDocument(segments=shuffled, format_name="srt")
    saved = save_subtitle(messy, tmp_path / "reordered.srt", "srt")
    reopened = load_subtitle(saved)
    assert [item.start_time for item in reopened.segments] == starts
    assert [item.source_text for item in reopened.segments] == [item.source_text for item in original.segments]
    assert reopened.segments[0].id == 1
    assert reopened.segments[-1].id == 1000


def test_format_conversion_preserves_time_and_text(tmp_path):
    source = load_subtitle(_assets() / "多语言.srt")
    conversions = [("vtt", 0), ("ass", 10), ("ssa", 10), ("srt", 0)]
    for fmt, tolerance in conversions:
        dest = tmp_path / f"converted.{fmt}"
        save_subtitle(source, dest, fmt)
        loaded = load_subtitle(dest)
        assert len(loaded.segments) == len(source.segments)
        for left, right in zip(source.segments, loaded.segments, strict=True):
            assert abs(left.start_time - right.start_time) <= tolerance
            assert abs(left.end_time - right.end_time) <= tolerance
            assert left.source_text.replace("\n", "\n") == right.source_text.replace("\\N", "\n")


def test_edit_save_reopen_does_not_lose_time_or_text(tmp_path):
    engine = FileSubtitleEngine()
    document = engine.load_document(_assets() / "多语言.srt")
    document.segments[0].source_text = "校正后的中文"
    document.segments[0].corrected_text = ""
    original_start = document.segments[0].start_time
    saved = engine.save_document(document, tmp_path / "edited.srt", "srt")
    reopened = engine.load_document(saved)
    assert reopened.segments[0].source_text == "校正后的中文"
    assert reopened.segments[0].start_time == original_start


def test_shift_jis_japanese(tmp_path):
    payload = "1\n00:00:00,000 --> 00:00:01,500\n字幕テスト：日本語\n"
    path = tmp_path / "日本語.srt"
    path.write_bytes(payload.encode("shift_jis"))
    document = load_subtitle(path)
    assert document.segments[0].source_text == "字幕テスト：日本語"
    assert document.encoding in {"shift_jis", "cp932"}


def test_abnormal_subtitles_do_not_crash():
    document = load_subtitle(_assets() / "异常字幕.srt")
    assert document.warnings
    texts = [item.source_text for item in document.segments]
    assert "有效条目" in texts
    assert "无序号也应导入" in texts
    assert all("时间颠倒" not in item.source_text for item in document.segments)


def test_empty_and_missing_files(tmp_path):
    empty = tmp_path / "empty.srt"
    empty.write_bytes(b"")
    with pytest.raises(SubtitleError, match="空"):
        load_subtitle(empty)
    with pytest.raises(SubtitleError, match="不存在"):
        load_subtitle(tmp_path / "missing.srt")


def test_ui_import_edit_save(qt_app, main_window, tmp_path):
    source = _assets() / "多语言.srt"
    main_window.add_subtitle_path(source)
    qt_app.processEvents()
    page = main_window.subtitle_page
    assert page.table.rowCount() == 5
    assert "你好" in (page.table.item(0, 4).text() or "")
    page.table.item(1, 4).setText("Edited English")
    qt_app.processEvents()
    dest = tmp_path / "from_ui.srt"
    document = page.document
    assert document is not None
    main_window.subtitle_engine.save_document(document, dest, "srt")
    reopened = FileSubtitleEngine().load_document(dest)
    assert reopened.segments[1].source_text == "Edited English"
    assert reopened.segments[1].start_time == parse_timestamp(page.table.item(1, 1).text())


def test_ui_loads_thousand_rows(qt_app, main_window):
    main_window.add_subtitle_path(_assets() / "一千条.srt")
    qt_app.processEvents()
    assert main_window.subtitle_page.table.rowCount() == 1000
    assert main_window.subtitle_page.table.item(999, 0).text() == "1000"


def test_list_embedded_uses_analyzer():
    video = install_root() / "test_assets" / "videos" / "phase3" / "多字幕.mkv"
    names = FileSubtitleEngine().list_embedded(video)
    assert len(names) == 2
    assert any("SRT" in name or "SUBRIP" in name.upper() for name in names)
