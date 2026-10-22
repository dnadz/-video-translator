from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from localvideoai import __version__
from localvideoai.batch.resources import can_start_another, snapshot
from localvideoai.core.exceptions import ExportError, MediaError, SpeechError, SubtitleError
from localvideoai.core.paths import install_root
from localvideoai.core.types import ExportRequest, TaskSpec
from localvideoai.db.database import Database
from localvideoai.engines import create_export_engine, create_speech_engine
from localvideoai.managers.json_project_manager import JsonProjectManager
from localvideoai.managers.sqlite_task_manager import SqliteTaskManager
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.performance.policy import policy_from_report
from localvideoai.performance.profiles import simulate_report
from localvideoai.project.recovery import RecoveryJournal
from localvideoai.speech.store import resolve_model_path
from localvideoai.subtitles.io import load_subtitle, save_subtitle
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument


def test_version_is_phase21():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 22)


def test_release_exes_exist():
    root = install_root() / "release"
    assert (root / "LocalVideoAI_Setup.exe").is_file()
    assert (root / "LocalVideoAI_Portable.exe").is_file()
    assert (root / "LocalVideoAI_Setup.exe").stat().st_size > 10_000_000
    assert (root / "LocalVideoAI_Portable.exe").stat().st_size > 10_000_000


def test_missing_video_and_corrupt_video_fail_clearly():
    missing = install_root() / "test_assets" / "videos" / "does-not-exist.mp4"
    with pytest.raises(MediaError):
        MediaAnalyzer().analyze(missing)
    corrupt = install_root() / "test_assets" / "videos" / "phase3" / "损坏.mp4"
    with pytest.raises(MediaError) as exc:
        MediaAnalyzer().analyze(corrupt)
    assert "损坏" in str(exc.value) or "无法" in str(exc.value)


def test_missing_and_corrupt_subtitles_do_not_crash(tmp_path):
    with pytest.raises(SubtitleError):
        load_subtitle(tmp_path / "missing.srt")
    garbage = tmp_path / "garbage.srt"
    garbage.write_bytes(bytes(range(256)) * 4)
    try:
        document = load_subtitle(garbage)
    except SubtitleError:
        return
    assert document.warnings or not document.segments


def test_missing_speech_model_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALVIDEOAI_MODELS_DIR", str(tmp_path / "empty-models"))
    monkeypatch.setenv("LOCALVIDEOAI_SKIP_BUNDLED_MODELS", "1")
    with pytest.raises(SpeechError) as exc:
        resolve_model_path("does-not-exist")
    assert "本地没有语音模型" in str(exc.value)


def test_corrupt_speech_model_fails_to_load(monkeypatch, tmp_path):
    root = tmp_path / "models" / "speech" / "broken"
    root.mkdir(parents=True)
    (root / "config.json").write_text('{"dim":1}\n', encoding="utf-8")
    (root / "model.bin").write_bytes(b"not-a-ctranslate2-model")
    monkeypatch.setenv("LOCALVIDEOAI_MODELS_DIR", str(tmp_path / "models"))
    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    with pytest.raises(SpeechError):
        create_speech_engine().transcribe_media(video, language="zh", model_id="broken", save_raw=False)


def test_ram_insufficient_refuses_new_batch_job():
    limits = snapshot(device="cpu", prefer_gpu=False, max_concurrent=4, min_free_ram_gb=10_000)
    allowed, reason = can_start_another(0, limits)
    assert allowed is False
    assert "内存" in reason


def test_low_vram_profile_stays_on_cpu():
    policy = policy_from_report(simulate_report("low"))
    assert policy.speech_device == "cpu"
    assert policy.prefer_gpu is False
    assert policy.max_background_jobs == 1


def test_export_missing_video_fails(tmp_path):
    with pytest.raises(ExportError):
        create_export_engine().export_detailed(
            ExportRequest(
                video_path=tmp_path / "missing.mp4",
                subtitle_path=None,
                output_path=tmp_path / "out.mp4",
                mode="sidecar",
                container="mp4",
                video_codec="copy",
            )
        )


def test_export_unwritable_destination_fails(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_bytes(b"not-a-dir")
    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    with pytest.raises(ExportError) as exc:
        create_export_engine().export_detailed(
            ExportRequest(
                video_path=video,
                subtitle_path=None,
                output_path=blocked / "out.mp4",
                mode="sidecar",
                container="mp4",
                video_codec="copy",
            )
        )
    assert "无法" in str(exc.value) or "导出" in str(exc.value)


def test_ffmpeg_crash_is_export_error(tmp_path, monkeypatch):
    fake_dir = tmp_path / "fake-ffmpeg"
    fake_dir.mkdir()
    fake = fake_dir / "ffmpeg.exe"
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    csc = windir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    source = tmp_path / "fail.cs"
    source.write_text(
        'class P{static int Main(){System.Console.Error.WriteLine("fake ffmpeg boom");return 1;}}',
        encoding="ascii",
    )
    compiled = subprocess.run(
        [str(csc), "/nologo", "/out:" + str(fake), str(source)],
        check=False,
        capture_output=True,
        text=True,
    )
    if compiled.returncode != 0 or not fake.is_file():
        pytest.skip(f"csc unavailable: {compiled.stderr}")
    monkeypatch.setenv("LOCALVIDEOAI_FFMPEG_DIR", str(fake_dir))
    video = install_root() / "test_assets" / "videos" / "10秒_测试.mp4"
    subtitle = tmp_path / "a.srt"
    save_subtitle(
        SubtitleDocument(
            segments=[SubtitleSegment(id=1, start_time=0, end_time=1000, source_text="qa")],
            format_name="srt",
        ),
        subtitle,
        "srt",
    )
    with pytest.raises((ExportError, MediaError)):
        create_export_engine().export_detailed(
            ExportRequest(
                video_path=video,
                subtitle_path=subtitle,
                output_path=tmp_path / "out.mp4",
                mode="sidecar",
                container="mp4",
                video_codec="copy",
            )
        )


def test_forced_close_can_restore_project(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALVIDEOAI_RECOVERY_DIR", str(tmp_path / "recovery"))
    projects = tmp_path / "projects"
    manager = JsonProjectManager()
    path = manager.create("强制关闭恢复", projects)
    data = manager.load(path)
    data["name"] = "强制关闭恢复"
    data["videos"] = [{"path": "clip.mp4", "name": "clip.mp4"}]
    manager.save(path, data)
    journal = RecoveryJournal(tmp_path / "recovery")
    journal.write_autosave(manager.load(path))
    journal.mark_dirty(path)
    unfinished = journal.unfinished()
    assert unfinished is not None
    restored = manager.load(path)
    assert restored["name"] == "强制关闭恢复"
    journal.mark_closed()
    assert journal.unfinished() is None


def test_forced_close_can_restore_tasks(tmp_path):
    db_path = tmp_path / "tasks.sqlite3"
    first = Database(db_path)
    first.connect()
    manager = SqliteTaskManager(first)
    task_id = manager.enqueue(TaskSpec(task_id="", task_type="batch_video", payload={"path": "clip.mp4"}))
    manager.update(task_id, status="识别", current_stage="speech")
    first.close()
    second = Database(db_path)
    second.connect()
    restored = SqliteTaskManager(second)
    task = restored.get(task_id)
    assert task is not None
    assert task["status"] == "识别"
    assert task["payload"].get("path") == "clip.mp4"
    second.close()
