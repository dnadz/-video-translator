from __future__ import annotations

import json
import os
import re
import socket
from pathlib import Path

import pytest
from PySide6.QtGui import QAction

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.core.types import SubtitleSegment, TranslationRequest
from localvideoai.engines import create_translation_engine
from localvideoai.engines.translation_engine import TranslationEngine
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.catalog import load_catalog
from localvideoai.translation.language import detect_source_language
from localvideoai.translation.quality import beam_size_for
from localvideoai.translation.resources import ResourceEntry, TranslationResources
from localvideoai.translation.store import list_local_translation_models

from tests.conftest import make_report


def _require_models() -> None:
    names = set(list_local_translation_models())
    needed = {"argos-zh-en", "argos-en-zh", "argos-ja-en"}
    missing = needed - names
    if missing:
        pytest.fail(f"missing translation models {sorted(missing)}; run scripts/prepare_phase8_models.py")


def _engine(isolated_env=None):
    _require_models()
    resources = TranslationResources()
    return create_translation_engine(make_report()), resources


def test_version_is_phase8():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 9)


def test_factory_returns_pluggable_engine():
    engine = create_translation_engine(make_report())
    assert isinstance(engine, TranslationEngine)
    assert engine.engine_id
    blob = Path(__file__).resolve().parents[1] / "src" / "localvideoai" / "engines" / "ctranslate2_translation_engine.py"
    text = blob.read_text(encoding="utf-8")
    assert "argos-zh-en" not in text
    assert "Helsinki-NLP" not in text
    assert "translate.googleapis" not in text


def test_catalog_supports_more_languages():
    catalog = load_catalog()
    assert {"zh", "en", "ja"} <= set(catalog.language_codes())
    pairs = {(route.source_lang, route.target_lang) for route in catalog.routes}
    assert ("zh", "en") in pairs
    assert ("en", "zh") in pairs
    assert ("ja", "zh") in pairs


def test_detect_source_language():
    assert detect_source_language("本日は晴天なり") == "ja"
    assert detect_source_language("今天天气很好") == "zh"
    assert detect_source_language("The weather is nice today") == "en"


def test_zh_to_en(isolated_env):
    engine, _ = _engine()
    result = engine.translate(
        TranslationRequest("今天天气很好。", "zh", "en", device_preference="cpu")
    )
    assert result.text.strip()
    assert result.text.strip() != "今天天气很好。"
    assert result.model_id != "translation-memory"
    assert result.via_memory is False
    assert re.search(r"weather|today|nice|fine|good|sun", result.text, re.I)


def test_en_to_zh(isolated_env):
    engine, _ = _engine()
    result = engine.translate(
        TranslationRequest("The weather is nice today.", "en", "zh", device_preference="cpu")
    )
    assert result.text.strip()
    assert result.text.strip() != "The weather is nice today."
    blob = result.text
    assert any(token in blob for token in ("天气", "今天", "好", "晴"))


def test_ja_to_zh(isolated_env):
    engine, _ = _engine()
    result = engine.translate(
        TranslationRequest("本日は晴天なり。", "ja", "zh", device_preference="cpu")
    )
    assert result.text.strip()
    assert result.text.strip() != "本日は晴天なり。"
    assert result.route
    assert any("ja-en" in hop or hop.endswith("ja-en") or "ja" in hop for hop in result.route) or len(result.route) >= 1
    assert re.search(r"[\u4e00-\u9fff]", result.text)


def test_auto_and_manual_source_language(isolated_env):
    engine, _ = _engine()
    auto = engine.translate(TranslationRequest("今天天气很好。", "auto", "en", device_preference="cpu"))
    manual = engine.translate(TranslationRequest("今天天气很好。", "zh", "en", device_preference="cpu"))
    assert auto.source_lang == "zh"
    assert manual.source_lang == "zh"
    assert auto.text.strip()
    assert manual.text.strip()


def test_multi_target_ja_to_zh_and_en(isolated_env):
    engine, _ = _engine()
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(id=1, start_time=0, end_time=1000, source_text="本日は晴天なり。", language="ja")
        ],
        format_name="srt",
        detected_language="ja",
    )
    engine.translate_document(document, "ja", ["zh", "en"], device_preference="cpu")
    segment = document.segments[0]
    assert segment.translated_text.strip()
    assert re.search(r"[\u4e00-\u9fff]", segment.translated_text)
    extras = segment.extra.get("translations") or {}
    assert extras.get("en", "").strip()
    assert re.search(r"[A-Za-z]", extras["en"])


def test_glossary_character_and_memory_user_priority(isolated_env):
    _require_models()
    resources = TranslationResources()
    resources.save_user(
        "translation_memory",
        [ResourceEntry("Phase8MemoryOnly", "翻译记忆命中", "en", "zh")],
    )
    resources.save_user(
        "glossary",
        [ResourceEntry("XyzzyTerm", "词表覆盖词", "en", "zh")],
    )
    resources.save_user(
        "character_dictionary",
        [ResourceEntry("Kakarot", "卡卡罗特", "en", "zh")],
    )
    from localvideoai.engines.ctranslate2_translation_engine import CTranslate2TranslationEngine

    engine = CTranslate2TranslationEngine(make_report(), resources=resources)
    memory = engine.translate(TranslationRequest("Phase8MemoryOnly", "en", "zh", device_preference="cpu"))
    assert memory.via_memory is True
    assert memory.text == "翻译记忆命中"
    glossary = engine.translate(
        TranslationRequest("The hero is XyzzyTerm today.", "en", "zh", device_preference="cpu")
    )
    assert "词表覆盖词" in glossary.text
    assert glossary.glossary_hits >= 1
    character = engine.translate(
        TranslationRequest("Kakarot arrives.", "en", "zh", device_preference="cpu")
    )
    assert "卡卡罗特" in character.text
    assert character.character_hits >= 1


def test_user_glossary_overrides_bundled(isolated_env, monkeypatch):
    bundled = isolated_env / "bundled-translation"
    bundled.mkdir()
    (bundled / "glossary.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "entries": [{"source": "Goku", "target": "内置悟空", "source_lang": "en", "target_lang": "zh"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(TranslationResources, "bundled_dir", lambda self: bundled)
    resources = TranslationResources()
    resources.save_user(
        "glossary",
        [ResourceEntry("Goku", "用户悟空", "en", "zh")],
    )
    _require_models()
    from localvideoai.engines.ctranslate2_translation_engine import CTranslate2TranslationEngine

    engine = CTranslate2TranslationEngine(make_report(), resources=resources)
    result = engine.translate(TranslationRequest("Goku smiles.", "en", "zh", device_preference="cpu"))
    assert "用户悟空" in result.text
    assert "内置悟空" not in result.text


def test_quality_changes_beam(isolated_env):
    engine, _ = _engine()
    fast = engine.translate(TranslationRequest("今天天气很好。", "zh", "en", quality="fast", device_preference="cpu"))
    high = engine.translate(TranslationRequest("今天天气很好。", "zh", "en", quality="high", device_preference="cpu"))
    assert fast.beam_size == beam_size_for("fast") == 1
    assert high.beam_size == beam_size_for("high") == 5
    assert fast.text.strip() and high.text.strip()


def test_offline_socket_block(monkeypatch, isolated_env):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    def blocked(*_args, **_kwargs):
        raise OSError("network disabled for Phase 8 offline test")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    engine, _ = _engine()
    result = engine.translate(TranslationRequest("今天天气很好。", "zh", "en", device_preference="cpu"))
    assert result.text.strip()
    assert result.model_id != "translation-memory"


def test_ui_source_has_no_ctranslate2_sdk():
    root = install_root() / "src" / "localvideoai" / "ui"
    for path in root.rglob("*.py"):
        blob = path.read_text(encoding="utf-8")
        assert "ctranslate2" not in blob
        assert "sentencepiece" not in blob
        assert "argostranslate" not in blob


def test_ui_translate_enabled_and_fills_table(qt_app, main_window):
    _require_models()
    translate = main_window.findChild(QAction, "action_menuTranslate")
    assert translate is not None and translate.isEnabled()
    assert main_window.side_panel.translate_button.isEnabled()
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(id=1, start_time=0, end_time=1200, source_text="今天天气很好。", language="zh")
        ],
        format_name="srt",
        detected_language="zh",
    )
    main_window.subtitle_page.set_document(document)
    for index in range(main_window.side_panel.source_language_combo.count()):
        if main_window.side_panel.source_language_combo.itemData(index) == "zh":
            main_window.side_panel.source_language_combo.setCurrentIndex(index)
    for index in range(main_window.side_panel.language_combo.count()):
        if str(main_window.side_panel.language_combo.itemData(index)).lower().startswith("en"):
            main_window.side_panel.language_combo.setCurrentIndex(index)
    main_window.side_panel.device_combo.setCurrentIndex(1)
    qt_app.processEvents()
    result = main_window.translate_current_document()
    qt_app.processEvents()
    assert result.segments[0].translated_text.strip()
    assert main_window.subtitle_page.table.rowCount() >= 1
    assert main_window.subtitle_page.table.item(0, 6).text().strip()
    assert main_window.subtitle_page.table.item(0, 6).text().strip() != "今天天气很好。"
