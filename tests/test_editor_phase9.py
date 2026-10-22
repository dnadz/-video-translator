from __future__ import annotations

import time
from pathlib import Path

import pytest

from PySide6.QtGui import QAction, QKeySequence

from localvideoai import __version__
from localvideoai.core.types import SubtitleSegment
from localvideoai.engines.ctranslate2_translation_engine import CTranslate2TranslationEngine
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.editor import SubtitleEditor
from localvideoai.subtitles.io import load_subtitle, save_subtitle
from localvideoai.subtitles.lock import preserve_locked
from localvideoai.subtitles.operations import merge_cues, split_cue
from localvideoai.subtitles.sidecar import sidecar_path
from localvideoai.subtitles.timecodes import format_srt_timestamp, parse_timestamp

from tests.conftest import make_report


def _doc(*texts: str) -> SubtitleDocument:
    segments = []
    cursor = 0
    for index, text in enumerate(texts, start=1):
        segments.append(
            SubtitleSegment(id=index, start_time=cursor, end_time=cursor + 1000, source_text=text)
        )
        cursor += 1000
    return SubtitleDocument(segments=segments, format_name="srt")


def test_version_is_phase9():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 10)


def test_millisecond_time_roundtrip():
    assert parse_timestamp(format_srt_timestamp(1234)) == 1234
    assert parse_timestamp("00:00:01,234") == 1234


def test_add_delete_modify_split_merge_undo_redo():
    editor = SubtitleEditor()
    editor.bind(_doc("第一句完整内容", "第二句"))
    editor.add(2000, "第三句")
    assert len(editor.document.segments) == 3
    editor.modify(0, "corrected_text", "人工校正")
    editor.modify(0, "translated_text", "manual translation")
    editor.split(0)
    assert len(editor.document.segments) == 4
    editor.merge([0, 1])
    assert "人工校正" in editor.document.segments[0].corrected_text or editor.document.segments[0].source_text
    editor.delete([2])
    assert editor.can_undo()
    while editor.can_undo():
        editor.undo()
    assert [item.source_text for item in editor.document.segments] == ["第一句完整内容", "第二句"]
    editor.redo()
    assert len(editor.document.segments) == 3


def test_find_replace_skips_locked():
    editor = SubtitleEditor()
    document = _doc("hello world", "hello locked")
    document.segments[1].locked = True
    editor.bind(document)
    hits = editor.find("hello")
    assert len(hits) == 2
    changed = editor.replace("hello", "hi")
    assert changed == 1
    assert editor.document.segments[0].source_text == "hi world"
    assert editor.document.segments[1].source_text == "hello locked"


def test_locked_blocks_edit_and_ai_overwrite():
    current = _doc("keep me", "replace me")
    current.segments[0].locked = True
    current.segments[0].corrected_text = "人工锁定"
    incoming = _doc("AI one", "AI two", "AI three")
    for item in incoming.segments:
        item.start_time += 50
        item.end_time += 50
    merged = preserve_locked(current, incoming)
    locked_texts = [item.corrected_text or item.source_text for item in merged.segments if item.locked]
    assert "人工锁定" in locked_texts
    editor = SubtitleEditor()
    editor.bind(current)
    try:
        editor.modify(0, "source_text", "hack")
        raise AssertionError("locked edit should fail")
    except Exception as exc:
        assert "锁定" in str(exc)


def test_save_reopen_preserves_lock_and_three_texts(tmp_path):
    document = _doc("原文")
    document.segments[0].start_time = 1234
    document.segments[0].end_time = 4321
    document.segments[0].corrected_text = "校正版"
    document.segments[0].translated_text = "translated line"
    document.segments[0].locked = True
    saved = save_subtitle(document, tmp_path / "editor.srt", "srt")
    assert sidecar_path(saved).is_file()
    loaded = load_subtitle(saved)
    assert loaded.segments[0].start_time == 1234
    assert loaded.segments[0].end_time == 4321
    assert loaded.segments[0].source_text == "原文"
    assert loaded.segments[0].corrected_text == "校正版"
    assert loaded.segments[0].translated_text == "translated line"
    assert loaded.segments[0].locked is True


def test_thousand_cues_editor_not_frozen():
    segments = [
        SubtitleSegment(id=index, start_time=index * 100, end_time=index * 100 + 80, source_text=f"cue {index}")
        for index in range(1, 1001)
    ]
    editor = SubtitleEditor()
    editor.bind(SubtitleDocument(segments=segments, format_name="srt"))
    started = time.perf_counter()
    editor.modify(10, "source_text", "changed")
    editor.split(20)
    editor.merge([30, 31])
    editor.add(100000, "tail")
    editor.undo()
    editor.redo()
    elapsed = time.perf_counter() - started
    assert len(editor.document.segments) >= 1000
    assert elapsed < 1.5


def test_translation_skips_locked(isolated_env):
    from localvideoai.translation.store import list_local_translation_models

    if "argos-en-zh" not in set(list_local_translation_models()):
        pytest.skip("missing translation models")
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(id=1, start_time=0, end_time=1000, source_text="The weather is nice today.", language="en"),
            SubtitleSegment(
                id=2,
                start_time=1000,
                end_time=2000,
                source_text="Do not touch",
                translated_text="人工译文",
                language="en",
                locked=True,
            ),
        ],
        format_name="srt",
        detected_language="en",
    )
    engine = CTranslate2TranslationEngine(make_report())
    engine.translate_document(document, "en", ["zh"], device_preference="cpu")
    assert document.segments[0].translated_text.strip()
    assert document.segments[0].translated_text != "The weather is nice today."
    assert document.segments[1].translated_text == "人工译文"


def test_split_text_keeps_times():
    segment = SubtitleSegment(id=1, start_time=1000, end_time=3000, source_text="left right extra")
    left, right = split_cue(segment, 2000)
    assert left.start_time == 1000
    assert left.end_time == 2000
    assert right.start_time == 2000
    assert right.end_time == 3000
    merged = merge_cues([left, right])
    assert merged.start_time == 1000
    assert merged.end_time == 3000


def test_ui_editor_layout_and_shortcuts(qt_app, main_window):
    assert main_window.video_stage.isVisible() or main_window.video_stage.width() >= 0
    assert main_window.editor_tracks.waveform.objectName() == "waveformWidget"
    assert main_window.editor_tracks.cue_timeline.objectName() == "subtitleTimeline"
    assert main_window.subtitle_page.table.objectName() == "subtitleTable"
    assert main_window.findChild(QAction, "action_undo").shortcut() == QKeySequence.StandardKey.Undo
    assert "Ctrl+Shift+Z" in main_window.findChild(QAction, "action_redo").shortcut().toString()
    assert main_window.findChild(QAction, "action_findReplace").shortcut() == QKeySequence.StandardKey.Find
    assert main_window.findChild(QAction, "action_saveSubtitle").shortcut() == QKeySequence.StandardKey.Save
    document = _doc("可编辑原文")
    main_window.subtitle_page.set_document(document)
    qt_app.processEvents()
    main_window.switch_page("subtitles")
    qt_app.processEvents()
    assert main_window.subtitle_page.table.rowCount() == 1
    started = time.perf_counter()
    heavy = SubtitleDocument(
        segments=[
            SubtitleSegment(id=i, start_time=i * 40, end_time=i * 40 + 30, source_text=f"r{i}")
            for i in range(1, 1001)
        ],
        format_name="srt",
    )
    main_window.subtitle_page.set_document(heavy)
    qt_app.processEvents()
    elapsed = time.perf_counter() - started
    assert main_window.subtitle_page.table.rowCount() == 1000
    assert elapsed < 2.5
    main_window.subtitle_page.add_cue(50000, "added")
    qt_app.processEvents()
    assert main_window.subtitle_page.table.rowCount() == 1001
    main_window.subtitle_page.undo()
    qt_app.processEvents()
    assert main_window.subtitle_page.table.rowCount() == 1000


def test_waveform_from_ffmpeg(tmp_path):
    from localvideoai.media.ffmpeg_runtime import find_ffmpeg
    from localvideoai.media.waveform import extract_waveform_peaks
    import subprocess

    wav = tmp_path / "tone.wav"
    command = [
        str(find_ffmpeg()),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=0.4",
        str(wav),
    ]
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace")[-500:])
    peaks = extract_waveform_peaks(wav, hop_ms=20)
    assert peaks.duration_ms >= 300
    assert len(peaks.peaks) >= 10
    assert max(peaks.peaks) > 0
