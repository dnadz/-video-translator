from __future__ import annotations

import ast
import inspect

from PySide6.QtGui import QAction, QColor

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.core.types import SubtitleCue, SubtitleSegment
from localvideoai.engines import create_quality_engine
from localvideoai.engines.quality_engine import QualityEngine
from localvideoai.quality.metrics import recognition_score
from localvideoai.quality.pipeline import apply_correction, next_issue_index
from localvideoai.quality.types import BAND_GREEN, BAND_RED, BAND_YELLOW, band_for
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import load_subtitle, save_subtitle
from localvideoai.subtitles.lock import preserve_locked
from localvideoai.translation.resources import ResourceEntry, TranslationResources


def _seg(
    cue_id: int,
    start: int,
    end: int,
    source: str,
    *,
    translated: str = "",
    confidence: float | None = None,
    locked: bool = False,
    extra: dict | None = None,
) -> SubtitleSegment:
    return SubtitleSegment(
        id=cue_id,
        start_time=start,
        end_time=end,
        source_text=source,
        translated_text=translated,
        confidence=confidence,
        locked=locked,
        extra=extra or {},
    )


def crafted_document() -> SubtitleDocument:
    return SubtitleDocument(
        format_name="srt",
        segments=[
            _seg(1, 0, 2000, "今天天气很好。", translated="The weather is nice today.", confidence=0.99),
            _seg(2, 2000, 4000, "我的的书包。", translated="My bag."),
            _seg(3, 4000, 6000, "你好世界。", translated=""),
            _seg(4, 7000, 9000, "重叠甲。", translated="Overlap A."),
            _seg(5, 8000, 10000, "重叠乙。", translated="Overlap B."),
            _seg(6, 11000, 12000, "一二三四五六七八九十甲乙丙丁戊己庚辛壬癸", translated="Too fast."),
            _seg(7, 13000, 21000, "短", translated="Long span."),
            _seg(8, 22000, 22400, "短句", translated="Too short."),
            _seg(9, 23000, 25000, "安全区", translated="Safe area.", extra={"ocr": {"x": 0.1, "y": 0.98, "w": 0.3, "h": 0.04}}),
            _seg(10, 26000, 28000, "损坏\ufffd文本", translated="Bad char."),
            _seg(11, 29000, 31000, "占位残留", translated="hello ZZG0ZZ"),
        ],
    )


def test_version_is_phase13():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 14)


def test_quality_engine_stays_abstract_and_factory_is_concrete():
    assert inspect.isabstract(QualityEngine)
    engine = create_quality_engine()
    assert isinstance(engine, QualityEngine)
    assert engine.engine_id
    assert engine.available()
    assert hasattr(engine, "inspect_document")


def test_bands_and_recognition_mapping():
    assert band_for(90) == BAND_GREEN
    assert band_for(89.9) == BAND_YELLOW
    assert band_for(70) == BAND_YELLOW
    assert band_for(69.9) == BAND_RED
    assert 70 < recognition_score(-0.2, True) < 90
    assert recognition_score(0.98, True) == 98
    assert recognition_score(None, True) == 80


def test_detects_required_issues_and_scores_are_deterministic():
    engine = create_quality_engine()
    document = crafted_document()
    first = engine.inspect_document(document, apply_fixes=False)
    second = engine.inspect_document(document, apply_fixes=False)
    assert [item.composite for item in first.cues] == [item.composite for item in second.cues]
    assert first.cues[0].composite >= 90
    assert first.cues[0].band == BAND_GREEN
    codes = {issue.code for cue in first.cues for issue in cue.issues}
    assert "typo" in codes
    assert "missing_translation" in codes
    assert "overlap" in codes
    assert "cps" in codes
    assert "reading_speed" in codes
    assert "too_long" in codes
    assert "too_short" in codes
    assert "safe_area" in codes
    assert "abnormal" in codes
    assert first.below_90
    assert 0 not in first.below_90
    assert any(item.band == BAND_YELLOW for item in first.cues)
    assert any(item.band == BAND_RED for item in first.cues)


def test_source_only_document_does_not_mass_flag_missing_translation():
    document = SubtitleDocument(
        format_name="srt",
        segments=[
            _seg(1, 0, 2000, "今天天气很好。", confidence=0.99),
            _seg(2, 2000, 4000, "第二句也完整。", confidence=0.99),
        ],
    )
    report = create_quality_engine().inspect_document(document, apply_fixes=False)
    assert all(item.code != "missing_translation" for cue in report.cues for item in cue.issues)
    assert report.cues[0].translation == 100
    assert report.cues[0].composite >= 90


def test_correction_skips_locked_cues():
    document = SubtitleDocument(
        format_name="srt",
        segments=[
            _seg(1, 0, 2000, "我的的书包。", locked=True),
            _seg(2, 2000, 4000, "我的的书包。", locked=False),
        ],
    )
    changed = apply_correction(document)
    assert changed == 1
    assert document.segments[0].source_text == "我的的书包。"
    assert document.segments[0].corrected_text == ""
    assert document.segments[1].corrected_text == "我的书包。"
    report = create_quality_engine().inspect_document(document, apply_fixes=True)
    assert document.segments[0].source_text == "我的的书包。"
    assert document.segments[0].corrected_text == ""
    assert any(item.code == "typo" for item in report.cues[0].issues)


def test_locked_cue_is_not_overwritten_by_incoming_ai():
    current = SubtitleDocument(
        format_name="srt",
        segments=[_seg(1, 0, 2000, "人工锁定原文", locked=True)],
    )
    incoming = SubtitleDocument(
        format_name="srt",
        segments=[_seg(1, 0, 2000, "AI 想覆盖")],
    )
    merged = preserve_locked(current, incoming)
    assert len(merged.segments) == 1
    assert merged.segments[0].source_text == "人工锁定原文"
    assert merged.segments[0].locked is True


def test_confirm_then_lock_and_filter_below_90():
    engine = create_quality_engine()
    document = crafted_document()
    report = engine.inspect_document(document, apply_fixes=False)
    assert report.below_90
    bad = report.below_90[0]
    engine.confirm_cue(document, bad)
    assert document.segments[bad].extra["qa"]["confirmed"] is True
    locked = engine.lock_confirmed(document)
    assert locked >= 1
    assert document.segments[bad].locked is True
    assert document.quality_stage in {"confirm", "lock", "qa"}
    nxt = next_issue_index(document, -1)
    assert nxt in report.below_90


def test_context_consistency_uses_glossary(tmp_path):
    resources = TranslationResources(user_dir=tmp_path)
    resources.save_user("glossary", [ResourceEntry(source="张三", target="Zhang San")])
    document = SubtitleDocument(
        format_name="srt",
        segments=[
            _seg(1, 0, 2000, "张三来了。", translated="Zhang San arrived."),
            _seg(2, 2000, 4000, "张三走了。", translated="John left."),
        ],
    )
    report = create_quality_engine().inspect_document(document, resources=resources, apply_fixes=False)
    assert any(item.code == "consistency" for item in report.cues[1].issues)
    assert report.cues[1].consistency < 90
    assert report.cues[0].consistency == 100


def test_sidecar_keeps_scores_and_stage(tmp_path):
    document = crafted_document()
    report = create_quality_engine().inspect_document(document, apply_fixes=False)
    dest = tmp_path / "quality.srt"
    save_subtitle(document, dest, "srt")
    loaded = load_subtitle(dest)
    assert loaded.quality_stage == "qa"
    assert loaded.segments[0].extra["qa"]["composite"] == report.cues[0].composite
    assert loaded.segments[0].extra["qa"]["band"] == BAND_GREEN


def test_score_cues_is_not_random():
    cues = [
        SubtitleCue(1, 0, 2000, "hello"),
        SubtitleCue(2, 1000, 3000, "overlap"),
    ]
    engine = create_quality_engine()
    assert engine.score(cues) == engine.score(cues)
    assert engine.score(cues)["overlap"] == 1


def test_ui_source_has_no_model_sdk():
    ui_dir = install_root() / "src" / "localvideoai" / "ui"
    forbidden = {"onnxruntime", "faster_whisper", "ctranslate2", "sentencepiece", "torch"}
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


def test_side_panel_has_quality_controls(main_window):
    panel = main_window.side_panel
    assert panel.quality_button.isEnabled()
    assert panel.quality_button.text() == "质量检查"
    assert panel.quality_filter_box.text() == "仅低于90分"
    assert panel.quality_jump_button.isEnabled()
    assert main_window.findChild(QAction, "action_menuQualityCheck") is not None
    assert main_window.subtitle_page.filter_below_90.text() == "仅低于90分"


def test_filter_below_90_and_jump(main_window, qt_app):
    page = main_window.subtitle_page
    page.set_document(crafted_document())
    main_window.run_quality_check()
    qt_app.processEvents()
    report = page.quality_report
    assert report is not None
    assert report.cues[0].composite >= 90
    assert 0 not in report.below_90
    page.set_filter_below_90(True)
    qt_app.processEvents()
    assert page.table.isRowHidden(0)
    visible_problem = next(index for index in report.below_90 if not page.table.isRowHidden(index))
    assert page.table.item(0, 0).background().color() == QColor(198, 239, 206)
    page.select_row(0)
    main_window.jump_quality_issue()
    qt_app.processEvents()
    selected = page.selected_indexes()
    assert selected
    assert selected[0] in report.below_90
    assert selected[0] == visible_problem or selected[0] in report.below_90
    assert "识别置信度" in page.quality_summary.text()
    assert page.issue_list.count() > 0
