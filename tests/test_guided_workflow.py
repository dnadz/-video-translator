from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog

from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument
from simplecaption.window import SimpleWindow


def make_window(tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"test fixture")
    window = SimpleWindow()
    window.set_media(media)
    return window


def document(translation=""):
    return SubtitleDocument(segments=[SubtitleSegment(id=1, start_time=0, end_time=1000,
        source_text="你好", translated_text=translation)], format_name="srt", detected_language="zh")


class FakeWorker(QObject):
    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__()

    def start(self):
        pass

    def isRunning(self):
        return False


def setup_fake_workers(monkeypatch, window):
    import simplecaption.window as module
    monkeypatch.setattr(module, "TranscribeWorker", FakeWorker)
    monkeypatch.setattr(module, "TranslateWorker", FakeWorker)
    monkeypatch.setattr(window, "_speech_engine", lambda: object())
    monkeypatch.setattr(window, "_translation_engine", lambda: object())
    monkeypatch.setattr(window, "_release_speech_model", lambda: None)
    monkeypatch.setattr(module, "transcript_to_document", lambda value: document())


def test_one_click_chains_only_after_recognition_finishes(qt_app, tmp_path, monkeypatch):
    w = make_window(tmp_path)
    setup_fake_workers(monkeypatch, w)
    w.start_pipeline()
    assert w._stage == "recognizing" and w._busy
    assert not w.start_button.isEnabled()
    assert not w.full_button.isEnabled()
    w._transcribe_worker.succeeded.emit(SimpleNamespace(language="zh", model_id="fake", device="cpu"))
    assert w._stage == "recognizing"
    w._transcribe_worker.finished.emit()
    assert w._stage == "translating" and w._busy
    w._translate_worker.succeeded.emit(document("Hello"))
    w._translate_worker.finished.emit()
    assert not w._busy and w._stage == "review"
    assert w._cover_worker is None
    assert w.export_button.isEnabled()
    w.close()


def test_stop_waits_for_recognition_and_prevents_translation(qt_app, tmp_path, monkeypatch):
    w = make_window(tmp_path)
    setup_fake_workers(monkeypatch, w)
    w.start_pipeline()
    w.stop_after_stage()
    assert w._busy
    w._transcribe_worker.succeeded.emit(SimpleNamespace(language="zh", model_id="fake", device="cpu"))
    w._transcribe_worker.finished.emit()
    assert not w._busy and w._translate_worker is None
    assert w._document.segments
    w.close()


def test_failure_does_not_advance_and_allows_retry(qt_app, tmp_path, monkeypatch):
    w = make_window(tmp_path)
    setup_fake_workers(monkeypatch, w)
    w.start_pipeline()
    w._transcribe_worker.failed.emit("模型缺失")
    w._transcribe_worker.finished.emit()
    assert w._stage == "failed"
    assert w._translate_worker is None and not w._busy
    assert w.start_button.isEnabled()
    w.close()


def test_empty_recognition_does_not_offer_a_false_completion(qt_app, tmp_path, monkeypatch):
    import simplecaption.window as module
    w = make_window(tmp_path)
    setup_fake_workers(monkeypatch, w)
    monkeypatch.setattr(module, "transcript_to_document", lambda value: SubtitleDocument(segments=[], format_name="srt"))
    w.start_pipeline()
    w._transcribe_worker.succeeded.emit(SimpleNamespace(language="en", model_id="fake", device="cpu"))
    w._transcribe_worker.finished.emit()
    assert w._stage == "empty" and w._translate_worker is None
    assert "没有识别到对白" in w.stage_label.text()
    w.close()


def test_full_workstation_hides_guided_window_and_returns_on_close(qt_app, tmp_path):
    from PySide6.QtCore import QCoreApplication, QEvent
    from localvideoai.managers.settings_manager import SettingsManager
    from tests.conftest import make_report
    w = SimpleWindow(SettingsManager(), make_report())
    w.show()
    w.open_full_mode()
    assert not w.isVisible() and w._full_window.isVisible()
    w._full_window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()
    assert w._full_window is None and w.isVisible()
    w.close()


def test_busy_cannot_replace_file_or_open_full_workstation(qt_app, tmp_path):
    w = make_window(tmp_path)
    original = w._media
    other = tmp_path / "other.mp4"
    other.write_bytes(b"other")
    w._set_busy(True)
    w.set_media(other)
    w.open_full_mode()
    assert w._media == original and w._full_window is None
    assert not w.table.isEnabled()
    w._set_busy(False)
    w.close()


def test_edits_are_exported_and_source_edit_invalidates_old_translation(qt_app, tmp_path, monkeypatch):
    w = make_window(tmp_path)
    w.show_document(document("Hello"))
    w.table.item(0, 3).setText("Good morning")
    output = tmp_path / "reviewed.srt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(output), ""))
    w.export_subtitles()
    assert "Good morning" in output.read_text(encoding="utf-8")
    w.table.item(0, 2).setText("早上好")
    assert w._document.segments[0].display_text() == "早上好"
    assert w._document.segments[0].translated_text == ""
    assert not w._validate_translation()
    w.close()


def test_switch_target_backs_up_old_language_and_disables_export(qt_app, tmp_path):
    w = make_window(tmp_path)
    w.show_document(document("Manually edited"))
    w.target_combo.setCurrentIndex(w.target_combo.findData("ja"))
    backup = w._output_dir / "clip.en.srt"
    assert "Manually edited" in backup.read_text(encoding="utf-8")
    assert not w.export_button.isEnabled()
    assert not w._document.segments[0].translated_text
    w.close()


def test_incomplete_translation_cannot_be_exported(qt_app, tmp_path):
    w = make_window(tmp_path)
    doc = document("Hello")
    doc.segments.append(SubtitleSegment(id=2, start_time=1200, end_time=2000, source_text="再见"))
    w.show_document(doc)
    assert not w._validate_translation()
    assert "1 句" in w.status.text()
    w.close()


def test_video_export_default_preserves_picture_and_original(tmp_path):
    import hashlib
    import subprocess
    from localvideoai.media.ffmpeg_runtime import find_ffmpeg
    from simplecaption.export_worker import export_captioned_video

    ffmpeg = str(find_ffmpeg())
    video = tmp_path / "original.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
        "color=c=blue:size=320x180:rate=10:duration=1", "-pix_fmt", "yuv420p", str(video)], check=True)
    before = hashlib.sha256(video.read_bytes()).hexdigest()
    srt = tmp_path / "translated.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    output = export_captioned_video(video, srt, tmp_path / "captioned.mp4")
    subprocess.run([ffmpeg, "-v", "error", "-i", str(output), "-f", "null", "-"], check=True)
    assert hashlib.sha256(video.read_bytes()).hexdigest() == before
    assert not list(tmp_path.glob("video-export-*"))
    assert output.stat().st_size > 1000


def test_failed_export_preserves_existing_output(tmp_path, monkeypatch):
    from simplecaption.export_worker import export_captioned_video
    import simplecaption.cover as cover
    destination = tmp_path / "existing.mp4"
    destination.write_bytes(b"keep this output")
    def fail(*args, **kwargs):
        raise RuntimeError("encoder failed")
    monkeypatch.setattr(cover, "cover_burned_subtitles", fail)
    import pytest
    with pytest.raises(RuntimeError):
        export_captioned_video(tmp_path / "original.mp4", tmp_path / "sub.srt", destination, blur=True)
    assert destination.read_bytes() == b"keep this output"
    assert not list(tmp_path.glob("video-export-*"))
