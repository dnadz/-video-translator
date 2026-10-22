from __future__ import annotations

import ast
import inspect
from pathlib import Path

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.core.types import SubtitleSegment
from localvideoai.managers.json_project_manager import JsonProjectManager
from localvideoai.managers.project_manager import ProjectManager
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.ocr.region import NormalizedRegion
from localvideoai.project.codec import ProjectTranslationResources, document_from_dict, document_to_dict
from localvideoai.project.recovery import RecoveryJournal
from localvideoai.project.schema import PROJECT_EXTENSION, REQUIRED_SECTIONS, empty_project
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.ui.main_window import MainWindow

from tests.conftest import make_report

VIDEO = install_root() / "test_assets" / "videos" / "phase15" / "clip_01.mp4"


def _document() -> SubtitleDocument:
    return SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=200,
                end_time=1400,
                source_text="批量测试01",
                corrected_text="批量测试01",
                translated_text="Batch test 01",
                speaker="Speaker 1",
                language="zh",
                locked=True,
                style_id="hero",
                extra={"qa": {"confirmed": True, "composite": 92}},
            ),
            SubtitleSegment(
                id=2,
                start_time=1500,
                end_time=2400,
                source_text="第二句",
                translated_text="Second line",
                speaker="Speaker 2",
                language="zh",
                locked=False,
            ),
        ],
        format_name="srt",
        detected_language="zh",
        speaker_map={"Speaker 1": "张三", "Speaker 2": "李四"},
        speaker_styles={"Speaker 1": "hero", "Speaker 2": "second"},
        quality_stage="qa",
    )


def test_version_is_phase16():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 17)


def test_project_manager_stays_abstract_and_vtproj_is_concrete():
    assert inspect.isabstract(ProjectManager)
    manager = JsonProjectManager()
    assert isinstance(manager, ProjectManager)
    assert not inspect.isabstract(JsonProjectManager)


def test_vtproj_contains_required_sections(tmp_path):
    manager = JsonProjectManager()
    path = manager.create("验收项目", tmp_path)
    assert path.suffix == PROJECT_EXTENSION
    data = manager.load(path)
    for key in REQUIRED_SECTIONS:
        assert key in data
    text = path.read_text(encoding="utf-8")
    assert text.startswith("{")
    assert "localvideoai-vtproj" in text


def test_legacy_project_json_still_loads(tmp_path):
    legacy = tmp_path / "project.json"
    legacy.write_text('{"name":"旧项目","videos":[{"path":"a.mp4","name":"a.mp4"}],"subtitles":[]}\n', encoding="utf-8")
    data = JsonProjectManager().load(legacy)
    assert data["name"] == "旧项目"
    assert data["videos"][0]["name"] == "a.mp4"
    assert "document" in data
    assert "locks" in data


def test_close_reopen_restores_full_state(qt_app, isolated_env):
    assert VIDEO.is_file()
    settings = SettingsManager()
    first = MainWindow(settings, make_report())
    first.show()
    qt_app.processEvents()
    folder = isolated_env / "中文项目目录"
    path = first.new_project("状态恢复", folder)
    assert path.suffix == PROJECT_EXTENSION
    first.add_video_path(VIDEO)
    first.subtitle_page.set_document(_document())
    first.translation_engine._resources = ProjectTranslationResources(
        {
            "glossary": [{"source": "张三", "target": "Zhang San", "source_lang": "zh", "target_lang": "en"}],
            "translation_memory": [],
            "character_dictionary": [{"source": "张三", "target": "Zhang San"}],
        }
    )
    first._ocr_region = NormalizedRegion(0.1, 0.72, 0.8, 0.2)
    first.side_panel.ocr_region_combo.setCurrentIndex(1)
    first.side_panel.language_combo.setCurrentIndex(first.side_panel.language_combo.findData("en"))
    first.side_panel.quality_combo.setCurrentIndex(first.side_panel.quality_combo.findData("high"))
    first.settings_page.export_format.setCurrentIndex(first.settings_page.export_format.findData("vtt"))
    first.settings_page.export_burn_in.setChecked(True)
    first.model_manager._active["speech"] = "speech/small"
    first._last_speech = {"language": "zh", "model_id": "small", "device": "cpu"}
    first._last_ocr = {"language": "zh", "model_id": "ppocrv6-small", "device": "cpu"}
    first.batch_runner.add_video(VIDEO)
    first._sync_project_from_tasks()
    first.playback.set_volume(0.4)
    first.playback.set_rate(1.25)
    saved = first.save_project()
    assert saved == path
    raw = path.read_text(encoding="utf-8")
    for needle in ("批量测试01", "Batch test 01", "张三", "speech/small", "vtt", "等待"):
        assert needle in raw
    first.close()
    qt_app.processEvents()

    second = MainWindow(SettingsManager(), make_report())
    second.show()
    qt_app.processEvents()
    second.open_project(path)
    qt_app.processEvents()
    document = second.subtitle_page.document
    assert document is not None
    assert document.segments[0].source_text == "批量测试01"
    assert document.segments[0].translated_text == "Batch test 01"
    assert document.segments[0].locked is True
    assert document.speaker_map["Speaker 1"] == "张三"
    assert document.speaker_styles["Speaker 1"] == "hero"
    assert document.segments[0].style_id == "hero"
    resources = second.translation_engine._resources
    assert any(item.source == "张三" for item in resources.load_user("glossary"))
    assert second._ocr_region is not None
    assert abs(second._ocr_region.y - 0.72) < 0.001
    assert second.side_panel.language_combo.currentData() == "en"
    assert second.side_panel.quality_combo.currentData() == "high"
    assert second.settings_page.export_format.currentData() == "vtt"
    assert second.settings_page.export_burn_in.isChecked()
    assert "small" in str(second.model_manager.active().get("speech") or "")
    assert "small" in str(second._last_speech.get("model_id") or "")
    assert any(item.get("path") == str(VIDEO.resolve()) for item in second.project_data().get("videos") or [])
    assert second.task_manager.list_tasks()
    assert document.segments[0].id in (second.project_data().get("locks") or {}).get("locked_ids", [1])
    second.close()
    qt_app.processEvents()


def test_autosave_and_crash_recover_abandon_save(qt_app, isolated_env):
    first = MainWindow(SettingsManager(), make_report())
    first.show()
    qt_app.processEvents()
    first.new_project("崩溃恢复", isolated_env / "crash")
    first.subtitle_page.set_document(_document())
    first.translation_engine._resources = ProjectTranslationResources(
        {"glossary": [{"source": "术语A", "target": "Term A"}], "translation_memory": [], "character_dictionary": []}
    )
    first._mark_project_dirty()
    autosave = first.autosave_project()
    assert autosave is not None and autosave.is_file()
    assert "术语A" in autosave.read_text(encoding="utf-8")
    first.close()
    qt_app.processEvents()

    journal = RecoveryJournal()
    pending = journal.unfinished()
    assert pending is not None
    assert pending.get("autosave") is not None

    second = MainWindow(SettingsManager(), make_report())
    second.show()
    qt_app.processEvents()
    recovered = second.recover_unfinished()
    assert recovered is not None
    assert second.subtitle_page.document is not None
    assert second.subtitle_page.document.segments[0].translated_text == "Batch test 01"
    assert any(item.source == "术语A" for item in second.translation_engine._resources.load_user("glossary"))
    dest = isolated_env / "crash" / "saved.vtproj"
    JsonProjectManager().save(dest, second.capture_project_state())
    assert dest.is_file()
    second.abandon_unfinished()
    assert RecoveryJournal().unfinished() is None
    second.close()
    qt_app.processEvents()

    third = MainWindow(SettingsManager(), make_report())
    third.open_project(dest)
    assert third.subtitle_page.document.segments[0].locked is True
    third.close()
    qt_app.processEvents()


def test_document_roundtrip_keeps_locks_and_speakers():
    original = _document()
    restored = document_from_dict(document_to_dict(original))
    assert restored is not None
    assert restored.segments[0].locked is True
    assert restored.speaker_map["Speaker 1"] == "张三"
    assert restored.segments[0].translated_text == "Batch test 01"


def test_recovery_journal_detects_dirty_and_clean(tmp_path):
    journal = RecoveryJournal(tmp_path / "recovery")
    assert journal.unfinished() is None
    journal.write_autosave(empty_project("未完成"))
    journal.mark_dirty()
    assert journal.unfinished() is not None
    journal.mark_closed()
    journal.clear()
    assert journal.unfinished() is None


def test_ui_has_no_model_sdk_imports():
    ui_dir = install_root() / "src" / "localvideoai" / "ui"
    forbidden = {"faster_whisper", "ctranslate2", "rapidocr", "onnxruntime", "torch", "cv2"}
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
