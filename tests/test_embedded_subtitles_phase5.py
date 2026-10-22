from __future__ import annotations

from pathlib import Path

import pytest

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.paths import install_root
from localvideoai.core.types import SubtitleTrackInfo
from localvideoai.engines.file_subtitle_engine import FileSubtitleEngine
from localvideoai.subtitles.extractor import is_bitmap_subtitle, unreadable_reason
from localvideoai.subtitles.language import detect_script_language, identify_language, language_display_name


def _phase5(name: str) -> Path:
    return install_root() / "test_assets" / "videos" / "phase5" / name


def _engine() -> FileSubtitleEngine:
    return FileSubtitleEngine()


def test_language_identification_zh_en_ja():
    assert detect_script_language("这是中文字幕") == "zh"
    assert detect_script_language("Hello from English") == "en"
    assert detect_script_language("こんにちは、世界。") == "ja"
    assert identify_language("这是中文字幕", "und") == "zh"
    assert identify_language("Hello from English", "eng") == "en"
    assert identify_language("こんにちは", "jpn") == "ja"
    assert language_display_name("chi") == "中文"
    assert language_display_name("eng") == "英文"
    assert language_display_name("jpn") == "日文"


def test_bitmap_codec_is_unreadable():
    assert is_bitmap_subtitle("dvd_subtitle", "VOBSUB")
    assert is_bitmap_subtitle("hdmv_pgs_subtitle", "PGS")
    reason = unreadable_reason("dvdsub", "VOBSUB")
    assert "不可读取" in reason
    track = SubtitleTrackInfo(index=2, codec="dvd_subtitle", format_name="VOBSUB", language="eng")
    assert track.codec == "dvd_subtitle"


def test_list_single_english_track():
    tracks = _engine().list_embedded_tracks(_phase5("单字幕_英文.mkv"))
    assert len(tracks) == 1
    assert tracks[0].language == "en"
    assert tracks[0].readable is True
    assert tracks[0].format_name in {"SRT", "SUBRIP"}


def test_list_multiple_tracks_zh_en_ja():
    tracks = _engine().list_embedded_tracks(_phase5("多字幕.mkv"))
    assert len(tracks) == 3
    languages = {item.language for item in tracks}
    assert {"en", "zh", "ja"} <= languages
    labels = _engine().list_embedded(_phase5("多字幕.mkv"))
    assert len(labels) == 3
    joined = "\n".join(labels)
    assert "SRT" in joined or "SUBRIP" in joined.upper()
    assert "ASS" in joined


def test_extract_single_english(tmp_path):
    video = _phase5("单字幕_英文.mkv")
    tracks = _engine().list_embedded_tracks(video)
    document = _engine().extract_embedded_document(video, tracks[0].index, tmp_path / "en.srt")
    assert document.segments
    assert "Hello from English" in document.segments[0].source_text
    assert document.segments[0].language == "en"
    assert document.detected_language == "en"
    assert all(hasattr(item, field) for item in document.segments for field in ("id", "start_time", "end_time", "source_text"))


def test_extract_single_chinese():
    video = _phase5("单字幕_中文.mkv")
    track = _engine().list_embedded_tracks(video)[0]
    document = _engine().extract_embedded_document(video, track.index)
    assert "这是中文字幕" in document.segments[0].source_text
    assert document.detected_language == "zh"
    assert document.segments[0].language == "zh"


def test_extract_single_japanese():
    video = _phase5("单字幕_日文.mkv")
    track = _engine().list_embedded_tracks(video)[0]
    document = _engine().extract_embedded_document(video, track.index)
    assert "こんにちは" in document.segments[0].source_text
    assert document.detected_language == "ja"
    assert document.segments[0].language == "ja"


def test_extract_each_track_from_multi():
    video = _phase5("多字幕.mkv")
    texts = []
    langs = []
    for track in _engine().list_embedded_tracks(video):
        document = _engine().extract_embedded_document(video, track.index)
        texts.append(document.segments[0].source_text)
        langs.append(document.detected_language)
        assert document.segments[0].id == 1
        assert document.segments[0].end_time > document.segments[0].start_time
    blob = "\n".join(texts)
    assert "Hello from English" in blob
    assert "中文" in blob
    assert "こんにちは" in blob
    assert "en" in langs
    assert "zh" in langs
    assert "ja" in langs


def test_detect_language_when_container_und():
    video = _phase5("无语言标记.mkv")
    track = _engine().list_embedded_tracks(video)[0]
    assert track.language == "und"
    document = _engine().extract_embedded_document(video, track.index)
    assert document.detected_language == "zh"
    assert "中文" in document.segments[0].source_text


def test_chinese_path_extract():
    video = _phase5("中文路径") / "多字幕.mkv"
    tracks = _engine().list_embedded_tracks(video)
    assert len(tracks) == 3
    document = _engine().extract_embedded_document(video, tracks[0].index)
    assert document.segments
    assert "中文路径" in str(video)


def test_preview_converts_to_internal_format():
    video = _phase5("单字幕_英文.mkv")
    track = _engine().list_embedded_tracks(video)[0]
    preview = _engine().preview_embedded(video, track.index)
    segment = preview.segments[0]
    for field in (
        "id",
        "start_time",
        "end_time",
        "speaker",
        "source_text",
        "corrected_text",
        "translated_text",
        "language",
        "confidence",
        "locked",
        "style_id",
    ):
        assert hasattr(segment, field)


def test_no_subtitle_track_is_error():
    with pytest.raises(SubtitleError, match="没有内嵌字幕"):
        _engine().extract_embedded_document(_phase5("无字幕.mp4"), 0)


def test_invalid_stream_index_is_error():
    video = _phase5("单字幕_英文.mkv")
    with pytest.raises(SubtitleError, match="不可读取"):
        _engine().extract_embedded_document(video, 999)


def test_empty_subtitle_track_is_error():
    video = _phase5("空字幕轨道.mkv")
    tracks = _engine().list_embedded_tracks(video)
    assert tracks
    with pytest.raises(SubtitleError, match="不可读取"):
        _engine().extract_embedded_document(video, tracks[0].index)


def test_ui_lists_and_extracts_without_breaking_playback(qt_app, main_window):
    video = _phase5("多字幕.mkv")
    main_window.add_video_path(video)
    qt_app.processEvents()
    page = main_window.subtitle_page
    assert page.track_combo.count() == 3
    assert main_window.timeline.play_button.isEnabled()
    source = main_window.playback.source_path
    preview = main_window.preview_embedded_subtitle()
    qt_app.processEvents()
    assert preview is not None
    assert page.preview_box.isVisible()
    assert "Hello from English" in page.preview_box.toPlainText() or "中文" in page.preview_box.toPlainText() or "こんにちは" in page.preview_box.toPlainText()
    document = main_window.extract_embedded_subtitle()
    qt_app.processEvents()
    assert document is not None
    assert page.table.rowCount() >= 1
    lang_item = page.table.item(0, 7)
    assert lang_item is not None and lang_item.text() in {"zh", "en", "ja"}
    assert main_window.playback.source_path == source
    assert main_window.timeline.play_button.isEnabled()


def test_ui_extract_error_does_not_stop_playback(qt_app, main_window):
    video = _phase5("单字幕_英文.mkv")
    main_window.add_video_path(video)
    qt_app.processEvents()
    source = main_window.playback.source_path
    assert source is not None
    enabled = main_window.timeline.play_button.isEnabled()
    with pytest.raises(SubtitleError):
        main_window.subtitle_engine.extract_embedded_document(video, 999)
    main_window.subtitle_page.track_combo.clear()
    result = main_window.extract_embedded_subtitle()
    qt_app.processEvents()
    assert result is None
    assert "没有可提取" in (main_window.subtitle_page.hint.text() or "") or "不可读取" in (
        main_window.subtitle_page.preview_box.toPlainText() or ""
    )
    assert main_window.playback.source_path == source
    assert main_window.timeline.play_button.isEnabled() == enabled


def test_ui_unreadable_track_keeps_video_playing(qt_app, main_window):
    video = _phase5("空字幕轨道.mkv")
    main_window.add_video_path(video)
    qt_app.processEvents()
    source = main_window.playback.source_path
    result = main_window.extract_embedded_subtitle()
    qt_app.processEvents()
    assert result is None
    assert "不可读取" in (main_window.subtitle_page.hint.text() or "") or "不可读取" in (
        main_window.subtitle_page.preview_box.toPlainText() or ""
    )
    assert main_window.playback.source_path == source
    assert main_window.timeline.play_button.isEnabled()
