from __future__ import annotations

import ast
import inspect
import json

import pytest

from localvideoai import __version__
from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.core.types import SubtitleCue, SubtitleSegment, TranslationRequest
from localvideoai.engines import create_translation_engine
from localvideoai.managers.context_manager import ContextManager
from localvideoai.managers.local_context_manager import LocalContextManager, create_context_manager
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import load_subtitle
from localvideoai.translation.context import chunk_ranges, context_hint_for, resolve_pronouns, window_policy
from localvideoai.translation.document import translate_document
from localvideoai.translation.resources import ResourceEntry
from localvideoai.translation.store import list_local_translation_models

from tests.conftest import make_report

PHASE11_SRT = install_root() / "test_assets" / "subtitles" / "phase11" / "context_en.srt"
COMPARE_LOG = install_root() / "logs" / "phase11_isolated_vs_context.json"

PHASE11_ENTRIES = [
    ResourceEntry("Dr. Elena Vargas", "瓦尔加斯医生", "en", "zh", "gender=female person"),
    ResourceEntry("Elena Vargas", "瓦尔加斯医生", "en", "zh", "gender=female person"),
    ResourceEntry("Vargas", "瓦尔加斯医生", "en", "zh", "gender=female person"),
    ResourceEntry("Nurse Wei", "小魏护士", "en", "zh", "gender=female person"),
    ResourceEntry("Wei", "小魏", "en", "zh", "gender=female person"),
    ResourceEntry("Harbor General Hospital", "海港总医院", "en", "zh", "place"),
    ResourceEntry("MRI scanner", "核磁共振仪", "en", "zh", "term"),
    ResourceEntry("contrast agent", "造影剂", "en", "zh", "term"),
]


def _require_models() -> None:
    names = set(list_local_translation_models())
    needed = {"argos-en-zh"}
    missing = needed - names
    if missing:
        pytest.fail(f"missing translation models {sorted(missing)}; run scripts/prepare_phase8_models.py")


def _engine():
    _require_models()
    return create_translation_engine(make_report())


def _document():
    return load_subtitle(PHASE11_SRT)


def test_version_is_phase11():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 12)


def test_context_manager_stays_abstract_and_local_is_concrete():
    assert inspect.isabstract(ContextManager)
    assert not inspect.isabstract(LocalContextManager)
    manager = create_context_manager("standard")
    assert isinstance(manager, ContextManager)
    assert manager.policy.prev == 6
    assert manager.policy.next == 1
    assert manager.policy.chunk_size == 120


def test_quality_windows_and_long_video_chunks():
    fast = window_policy("极速")
    standard = window_policy("标准")
    high = window_policy("高质量")
    assert (fast.prev, fast.next, fast.chunk_size, fast.max_chars) == (2, 0, 40, 180)
    assert (standard.prev, standard.next, standard.chunk_size, standard.max_chars) == (6, 1, 120, 480)
    assert (high.prev, high.next, high.chunk_size, high.max_chars) == (16, 2, 240, 1200)
    ranges = chunk_ranges(100, fast.chunk_size)
    assert [list(item) for item in ranges] == [list(range(0, 40)), list(range(40, 80)), list(range(80, 100))]
    manager = create_context_manager("fast")
    assert [list(item) for item in manager.chunk_ranges(85)] == [
        list(range(0, 40)),
        list(range(40, 80)),
        list(range(80, 85)),
    ]
    assert "前 2 条" in context_hint_for("fast")
    assert "每 240 条" in context_hint_for("high")


def test_build_context_respects_window_and_max_chars():
    cues = [
        SubtitleCue(index=i, start_ms=i * 1000, end_ms=i * 1000 + 800, text=f"line {i} " + ("x" * 80))
        for i in range(8)
    ]
    small = create_context_manager("fast")
    context = small.build_context(cues, 5)
    assert "line 5" not in context
    assert "PREV" in context
    assert "line 3" in context or "line 4" in context
    assert "line 0" not in context
    assert len(context) <= small.policy.max_chars
    high = create_context_manager("high")
    wide = high.build_context(cues, 5)
    assert "NEXT" in wide
    assert "line 6" in wide


def test_pronoun_and_memory_prepare_without_model():
    manager = create_context_manager("standard", extra_entries=PHASE11_ENTRIES)
    first = manager.prepare(
        "Dr. Elena Vargas arrived at Harbor General Hospital.",
        "en",
        "zh",
        "PREV none",
    )
    assert first.pronoun_rewritten is False
    assert ("Harbor General Hospital", "海港总医院") in first.force_terms
    assert manager.memory.last_person is not None
    assert manager.memory.last_person.source == "Dr. Elena Vargas"
    second = manager.prepare("She asked Nurse Wei to prepare the MRI scanner.", "en", "zh")
    assert second.pronoun_rewritten is True
    assert "Dr. Elena Vargas" in second.text
    assert ("MRI scanner", "核磁共振仪") in second.force_terms
    assert ("Nurse Wei", "小魏护士") in second.force_terms
    rewritten, changed = resolve_pronouns("She left.", manager.memory.last_person, "en")
    assert changed is True
    assert "Elena Vargas" in rewritten or "Vargas" in rewritten


def test_session_translation_memory_reuses_sentence(isolated_env):
    _require_models()
    engine = _engine()
    manager = create_context_manager("standard", extra_entries=PHASE11_ENTRIES)
    document = SubtitleDocument(
        format_name="srt",
        segments=[
            SubtitleSegment(1, 0, 1000, source_text="The MRI scanner was calibrated last night."),
            SubtitleSegment(2, 1000, 2000, source_text="The MRI scanner was calibrated last night."),
        ],
    )
    results = translate_document(
        engine,
        document,
        "en",
        ["zh"],
        quality="standard",
        device_preference="cpu",
        prefer_gpu=False,
        context_manager=manager,
    )
    assert len(results) == 2
    assert results[0].text.strip()
    assert results[1].text == results[0].text
    assert results[1].via_memory is True
    assert results[1].model_id == "session-translation-memory"
    assert results[1].context_used is True


def test_engine_uses_force_terms_and_context_flag(isolated_env):
    engine = _engine()
    bare = engine.translate(
        TranslationRequest("The MRI scanner is ready.", "en", "zh", device_preference="cpu")
    )
    contextual = engine.translate(
        TranslationRequest(
            "The MRI scanner is ready.",
            "en",
            "zh",
            context="PREV Dr. Elena Vargas arrived at Harbor General Hospital.",
            force_terms=(("MRI scanner", "核磁共振仪"),),
            device_preference="cpu",
        )
    )
    assert contextual.context_used is True
    assert "核磁共振仪" in contextual.text
    assert contextual.text != bare.text or "核磁共振仪" not in bare.text


def test_isolated_vs_context_translation(isolated_env):
    engine = _engine()
    isolated_doc = _document()
    context_doc = _document()
    manager = create_context_manager("standard", extra_entries=PHASE11_ENTRIES)
    isolated = translate_document(
        engine,
        isolated_doc,
        "en",
        ["zh"],
        quality="standard",
        device_preference="cpu",
        prefer_gpu=False,
        use_context=False,
    )
    contextual = translate_document(
        engine,
        context_doc,
        "en",
        ["zh"],
        quality="standard",
        device_preference="cpu",
        prefer_gpu=False,
        context_manager=manager,
    )
    assert len(isolated) == 6
    assert len(contextual) == 6
    assert all(item.text.strip() for item in isolated)
    assert all(item.text.strip() for item in contextual)
    isolated_rows = [
        {
            "index": index + 1,
            "source": isolated_doc.segments[index].source_text,
            "translated": isolated[index].text,
            "context_used": isolated[index].context_used,
        }
        for index in range(6)
    ]
    context_rows = [
        {
            "index": index + 1,
            "source": context_doc.segments[index].source_text,
            "rewritten": context_doc.segments[index].extra.get("context_rewritten"),
            "applied": context_doc.segments[index].extra.get("context_applied"),
            "translated": contextual[index].text,
            "context_used": contextual[index].context_used,
        }
        for index in range(6)
    ]
    ensure_directory(COMPARE_LOG.parent)
    COMPARE_LOG.write_text(
        json.dumps(
            {"isolated": isolated_rows, "context": context_rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    she_line = context_doc.segments[1].extra.get("context_rewritten") or ""
    assert "Dr. Elena Vargas" in she_line
    assert "She asked" not in she_line
    assert isolated_doc.segments[1].extra.get("context_rewritten") in {None, "She asked Nurse Wei to prepare the MRI scanner."}
    context_zh = "\n".join(item.text for item in contextual)
    assert "瓦尔加斯" in contextual[1].text
    assert "海港总医院" in contextual[0].text
    assert "海港总医院" in contextual[5].text
    assert context_zh.count("核磁共振仪") >= 2
    assert context_zh.count("造影剂") >= 2
    assert any(row["translated"] != isolated_rows[index]["translated"] for index, row in enumerate(context_rows))
    assert all(item.context_used for item in contextual)
    assert not any(item.context_used for item in isolated)


def test_ui_source_has_no_model_sdk():
    ui_dir = install_root() / "src" / "localvideoai" / "ui"
    forbidden = {"faster_whisper", "ctranslate2", "sentencepiece", "torch"}
    offenders: list[str] = []
    for path in ui_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in forbidden:
                    offenders.append(f"{path.name} imports {name}")
    assert offenders == []


def test_side_panel_shows_context_hint(main_window):
    hint = main_window.side_panel.context_hint.text()
    assert "前 6 条" in hint
    combo = main_window.side_panel.quality_combo
    combo.setCurrentIndex(0)
    assert "前 2 条" in main_window.side_panel.context_hint.text()
    combo.setCurrentIndex(2)
    assert "前 16 条" in main_window.side_panel.context_hint.text()
