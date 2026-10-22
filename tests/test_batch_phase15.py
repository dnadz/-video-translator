from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import time
from pathlib import Path

from localvideoai import __version__
from localvideoai.batch.resources import can_start_another, snapshot
from localvideoai.batch.runner import BatchRunner
from localvideoai.batch.types import (
    STATUS_DONE,
    STATUS_FAIL,
    STATUS_PAUSE,
    STATUS_WAIT,
)
from localvideoai.core.paths import install_root
from localvideoai.core.types import TaskSpec
from localvideoai.db.database import Database
from localvideoai.engines import (
    create_ocr_engine,
    create_quality_engine,
    create_speech_engine,
    create_translation_engine,
)
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.managers.sqlite_task_manager import SqliteTaskManager, create_task_manager
from localvideoai.managers.task_manager import TaskManager
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.ocr.store import is_ocr_ready
from localvideoai.speech.store import list_local_models
from localvideoai.translation.store import list_local_translation_models
from localvideoai.ui.main_window import MainWindow
from localvideoai.ui.pages.batch_page import format_eta

from tests.conftest import make_report

VIDEOS = install_root() / "test_assets" / "videos" / "phase15"


def _video_paths() -> list[Path]:
    paths = [VIDEOS / f"clip_{index:02d}.mp4" for index in range(1, 11)]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise AssertionError(f"missing {missing}; run scripts/prepare_phase15_videos.py")
    if not is_ocr_ready():
        raise AssertionError("no local OCR model; run scripts/prepare_phase7_models.py")
    if not list_local_models():
        raise AssertionError("no local speech model; run scripts/prepare_phase6_models.py")
    if not list_local_translation_models():
        raise AssertionError("no local translation model; run scripts/prepare_phase8_models.py")
    return paths


def _open_manager(path: Path) -> SqliteTaskManager:
    database = Database(path)
    database.connect()
    return SqliteTaskManager(database)


def _make_runner(manager: TaskManager, **overrides) -> BatchRunner:
    kwargs = {
        "analyzer": overrides.pop("analyzer", None) or MediaAnalyzer(),
        "speech_engine": overrides.pop("speech_engine", None) or create_speech_engine(),
        "ocr_engine": overrides.pop("ocr_engine", None) or create_ocr_engine(),
        "translation_engine": overrides.pop("translation_engine", None) or create_translation_engine(),
        "quality_engine": overrides.pop("quality_engine", None) or create_quality_engine(),
        "device": "cpu",
        "prefer_gpu": False,
        "max_concurrent": 1,
        "target_lang": "en",
    }
    kwargs.update(overrides)
    return BatchRunner(manager, **kwargs)


def test_version_is_phase15():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 16)


def test_task_manager_stays_abstract_and_sqlite_is_concrete():
    assert inspect.isabstract(TaskManager)
    assert not inspect.isabstract(SqliteTaskManager)
    manager = create_task_manager()
    assert isinstance(manager, TaskManager)
    assert hasattr(manager, "update")
    assert hasattr(manager, "delete")


def test_status_vocabulary():
    from localvideoai.batch import types

    assert types.STATUS_WAIT == "等待"
    assert types.STATUS_ANALYZE == "分析"
    assert types.STATUS_SPEECH == "识别"
    assert types.STATUS_OCR == "OCR"
    assert types.STATUS_TRANSLATE == "翻译"
    assert types.STATUS_REVIEW == "校对"
    assert types.STATUS_EXPORT == "导出"
    assert types.STATUS_DONE == "完成"
    assert types.STATUS_FAIL == "失败"
    assert types.STATUS_PAUSE == "暂停"


def test_resources_and_eta_helpers():
    limits = snapshot(device="cpu", prefer_gpu=False, max_concurrent=1, min_free_ram_gb=0)
    assert limits.cpu_count >= 1
    assert limits.total_ram_gb >= 0
    allowed, reason = can_start_another(1, limits)
    assert allowed is False
    assert "并发" in reason
    assert format_eta(None) == "计算中"
    assert format_eta(75) == "01:15"


def test_cancel_retry_delete_and_skip_completed(tmp_path):
    manager = _open_manager(tmp_path / "tasks.sqlite3")
    runner = _make_runner(manager)
    waiting = runner.add_video(tmp_path / "missing-a.mp4")
    done_id = runner.add_video(tmp_path / "missing-b.mp4")
    extra = runner.add_video(tmp_path / "missing-c.mp4")
    manager.update(
        done_id,
        status=STATUS_DONE,
        done_stages=["analyze", "speech", "ocr", "translate", "review", "export"],
    )
    runner.cancel(waiting)
    assert manager.get(waiting)["status"] == STATUS_FAIL
    assert manager.get(waiting)["payload"].get("error") == "已取消"
    runner.retry(waiting)
    assert manager.get(waiting)["status"] == STATUS_WAIT
    runner.delete(extra)
    assert manager.get(extra) is None
    runner.run_until_idle()
    assert manager.get(done_id)["status"] == STATUS_DONE
    assert manager.get(waiting)["status"] == STATUS_FAIL
    assert "不存在" in str(manager.get(waiting)["payload"].get("error") or "")


def test_ten_videos_pause_persist_reopen_continue(tmp_path):
    if _run_isolated("test_ten_videos_pause_persist_reopen_continue"):
        return
    videos = _video_paths()
    db_path = tmp_path / "batch.sqlite3"
    manager = _open_manager(db_path)
    speech = create_speech_engine()
    ocr = create_ocr_engine()
    translation = create_translation_engine()
    quality = create_quality_engine()
    analyzer = MediaAnalyzer()
    runner = _make_runner(
        manager,
        analyzer=analyzer,
        speech_engine=speech,
        ocr_engine=ocr,
        translation_engine=translation,
        quality_engine=quality,
    )
    ids = [runner.add_video(path) for path in videos]
    assert len(ids) == 10

    def pause_after_first_stage() -> None:
        if runner.is_paused():
            return
        for task in manager.list_tasks():
            done = list((task.get("payload") or {}).get("done_stages") or [])
            if done or task.get("status") not in {STATUS_WAIT, STATUS_PAUSE}:
                runner.pause()
                return

    runner._on_change = pause_after_first_stage
    runner.run_until_idle()
    after_pause = manager.list_tasks()
    assert len(after_pause) == 10
    assert any(item.get("status") == STATUS_DONE for item in after_pause) or any(
        (item.get("payload") or {}).get("done_stages") for item in after_pause
    )
    assert any(item.get("status") != STATUS_DONE for item in after_pause)
    manager.close()

    restored = _open_manager(db_path)
    resumed = _make_runner(
        restored,
        analyzer=analyzer,
        speech_engine=speech,
        ocr_engine=ocr,
        translation_engine=translation,
        quality_engine=quality,
    )
    completed_before = {item["id"] for item in restored.list_tasks() if item.get("status") == STATUS_DONE}
    resumed.run_until_idle()
    final = restored.list_tasks()
    assert len(final) == 10
    statuses = {item["status"] for item in final}
    assert statuses <= {STATUS_DONE, STATUS_FAIL}
    assert sum(1 for item in final if item["status"] == STATUS_DONE) >= 8
    for task_id in completed_before:
        assert restored.get(task_id)["status"] == STATUS_DONE
    exported = 0
    for task in final:
        export_path = Path(str((task.get("payload") or {}).get("export_path") or ""))
        if export_path.is_file():
            exported += 1
            text = export_path.read_text(encoding="utf-8")
            assert "批量测试" in text or "-->" in text
    assert exported >= 8
    stats = resumed.stats()
    assert "speed_per_min" in stats
    assert "eta_seconds" in stats
    assert stats["speed_per_min"] >= 0
    assert stats["done"] >= 8


def test_ui_ten_videos_close_reopen_continue(qt_app, isolated_env):
    if _run_isolated("test_ui_ten_videos_close_reopen_continue"):
        return
    videos = _video_paths()
    settings = SettingsManager()
    first = MainWindow(settings, make_report())
    first.show()
    qt_app.processEvents()
    first.batch_page.device_combo.setCurrentIndex(first.batch_page.device_combo.findData("cpu"))
    first.batch_page.concurrent_spin.setValue(1)
    lang = first.side_panel.language_combo.findData("en")
    if lang >= 0:
        first.side_panel.language_combo.setCurrentIndex(lang)
    first._settings.set("app.target_language", "en")
    for path in videos:
        first.add_batch_path(path)
    assert first.batch_page.table.rowCount() == 10
    assert first.batch_page.start_button.isEnabled()
    first.start_batch()

    def _any_progress() -> bool:
        return any(
            item.get("status") not in {STATUS_WAIT} or (item.get("payload") or {}).get("done_stages")
            for item in first.task_manager.list_tasks()
        )

    _pump(qt_app, _any_progress, timeout=180, label="first stage")
    first.pause_batch()
    _pump(qt_app, lambda: first._batch_worker is None or not first._batch_worker.isRunning(), timeout=180, label="pause idle")
    first.close()
    qt_app.processEvents()

    second = MainWindow(SettingsManager(), make_report())
    second.show()
    qt_app.processEvents()
    second.batch_page.device_combo.setCurrentIndex(second.batch_page.device_combo.findData("cpu"))
    second.batch_page.concurrent_spin.setValue(1)
    second._settings.set("app.target_language", "en")
    assert second.batch_page.table.rowCount() == 10
    statuses = [second.batch_page.table.item(row, 1).text() for row in range(10)]
    assert all(status for status in statuses)
    second.resume_batch()
    _pump(
        qt_app,
        lambda: all(item.get("status") in {STATUS_DONE, STATUS_FAIL} for item in second.task_manager.list_tasks())
        and (second._batch_worker is None or not second._batch_worker.isRunning()),
        timeout=1200,
        label="finish after reopen",
    )
    done = [item for item in second.task_manager.list_tasks() if item.get("status") == STATUS_DONE]
    assert len(done) >= 8
    assert "速度" in second.batch_page.stats_label.text()
    assert "预计剩余" in second.batch_page.stats_label.text()
    second.close()
    qt_app.processEvents()


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


def _run_isolated(test_id: str) -> bool:
    """Run GPU-heavy batch jobs in a child process so later tests keep a clean runtime."""
    marker = f"LOCALVIDEOAI_BATCH_INNER_{test_id}"
    if os.environ.get(marker) == "1":
        return False
    env = os.environ.copy()
    env[marker] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", f"{Path(__file__).name}::{test_id}", "-q", "--tb=short"],
        cwd=str(Path(__file__).parent),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise AssertionError((completed.stdout or "") + "\n" + (completed.stderr or ""))
    return True


def _pump(qt_app, predicate, timeout: float, label: str) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qt_app.processEvents()
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {label}")
