from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QTimer, QUrl, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from localvideoai import APP_DISPLAY_NAME, __version__
from localvideoai.batch.runner import BatchRunner
from localvideoai.core.exceptions import ExportError, MediaError, ModelError, PathError, SubtitleError, TranslationError
from localvideoai.core.paths import bundled_models_dir, cache_dir, logs_dir, projects_dir, set_cache_dir, set_projects_dir
from localvideoai.core.types import ExportRequest, TaskSpec
from localvideoai.engines import (
    create_export_engine,
    create_inpainting_engine,
    create_ocr_engine,
    create_quality_engine,
    create_speaker_engine,
    create_speech_engine,
    create_translation_engine,
)
from localvideoai.engines.ffmpeg_audio_engine import FFmpegAudioEngine
from localvideoai.engines.ffmpeg_video_engine import FFmpegVideoEngine
from localvideoai.engines.file_subtitle_engine import FileSubtitleEngine
from localvideoai.hardware.hardware_manager import EnvironmentReport, HardwareManager
from localvideoai.managers.json_project_manager import JsonProjectManager, empty_project
from localvideoai.managers.local_model_manager import LocalModelManager
from localvideoai.managers.log_manager import get_logger
from localvideoai.managers.project_manager import ProjectManager
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.managers.sqlite_task_manager import create_task_manager
from localvideoai.ocr.persist import ocr_to_document
from localvideoai.ocr.region import NormalizedRegion
from localvideoai.project.codec import (
    ProjectTranslationResources,
    analysis_from_dict,
    analysis_to_dict,
    document_from_dict,
    document_to_dict,
    entries_from_json,
    entries_to_json,
    lock_ids,
)
from localvideoai.project.recovery import RecoveryJournal
from localvideoai.project.schema import merge_project, normalize_project_path
from localvideoai.release.diagnostics import export_crash_bundle
from localvideoai.release.license import load_license, save_license
from localvideoai.ocr.sampler import extract_still
from localvideoai.speech.persist import transcript_to_document
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.media.playback_controller import PlaybackController, collect_video_paths
from localvideoai.performance.runtime import PerformanceRuntime
from localvideoai.ui import strings
from localvideoai.ui.availability import unlock_action
from localvideoai.subtitles.lock import preserve_locked
from localvideoai.ui.dialogs.export_dialog import ExportDialog
from localvideoai.ui.dialogs.recovery import ABANDON, RECOVER, SAVE, ask_unfinished
from localvideoai.ui.dialogs.find_replace import FindReplaceDialog
from localvideoai.ui.dialogs.region_picker import RegionPickerDialog
from localvideoai.ui.dialogs.speaker_map import SpeakerMapDialog
from localvideoai.ui.dialogs.translation_resources import TranslationResourcesDialog
from localvideoai.ui.pages.batch_page import BatchPage
from localvideoai.ui.pages.models_page import ModelsPage
from localvideoai.ui.pages.project_page import ProjectPage
from localvideoai.ui.pages.settings_page import SettingsPage
from localvideoai.ui.pages.subtitle_page import SubtitlePage
from localvideoai.ui.panels.editor_tracks import EditorTracksPanel
from localvideoai.ui.panels.project_list_panel import ProjectListPanel
from localvideoai.ui.panels.side_panel import SidePanel
from localvideoai.ui.panels.timeline_panel import TimelinePanel
from localvideoai.ui.panels.video_stage import VideoStage
from localvideoai.ui.theme import apply_theme
from localvideoai.realtime.policy import adjust_window_ms, normalize_delay_ms, normalize_profile, profile_settings
from localvideoai.ui.workers.batch_worker import BatchWorker
from localvideoai.ui.workers.export_worker import ExportWorker
from localvideoai.ui.workers.inpaint_worker import InpaintWorker
from localvideoai.ui.workers.model_worker import ModelWorker
from localvideoai.ui.workers.ocr_worker import OCRWorker
from localvideoai.ui.workers.realtime_worker import RealtimeWorker
from localvideoai.ui.workers.speaker_worker import SpeakerWorker
from localvideoai.ui.workers.transcribe_worker import TranscribeWorker
from localvideoai.ui.workers.translate_worker import TranslateWorker
from localvideoai.ui.workers.waveform_worker import WaveformWorker
from localvideoai.translation.language import normalize_translation_language
from localvideoai.translation.resources import TranslationResources

PAGES = (
    ("workspace", strings.WORKSPACE),
    ("subtitles", strings.SUBTITLES),
    ("batch", strings.BATCH),
    ("models", strings.MODELS),
    ("projects", strings.PROJECTS),
    ("settings", strings.SETTINGS),
)

VIDEO_FILTER = "视频文件 (*.mp4 *.mkv *.avi *.mov *.webm *.ts);;所有文件 (*.*)"
SUBTITLE_FILTER = "字幕文件 (*.srt *.ass *.ssa *.vtt);;所有文件 (*.*)"
PROJECT_FILTER = "LocalVideoAI 项目 (*.vtproj);;旧版项目 (project.json);;JSON (*.json)"


class MainWindow(QMainWindow):
    """Windows 11 local subtitle workstation shell."""

    def __init__(
        self,
        settings: SettingsManager,
        report: EnvironmentReport,
        project_manager: ProjectManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._report = report
        self._perf = PerformanceRuntime(report)
        self._projects = project_manager or JsonProjectManager()
        self._logger = get_logger("ui")
        self._project: dict[str, Any] = empty_project("未命名项目")
        self._project_path: Path | None = None
        self._current_page = "workspace"
        self.playback = PlaybackController(self)
        self.video_engine = FFmpegVideoEngine()
        self.audio_engine = FFmpegAudioEngine()
        self.media_analyzer = MediaAnalyzer()
        self.subtitle_engine = FileSubtitleEngine()
        self.speech_engine = create_speech_engine(report)
        self.ocr_engine = create_ocr_engine(report)
        self.translation_engine = create_translation_engine(report)
        self.speaker_engine = create_speaker_engine(report)
        self.quality_engine = create_quality_engine(report)
        self.inpaint_engine = create_inpainting_engine(report, self.ocr_engine)
        self.export_engine = create_export_engine()
        self.model_manager = LocalModelManager(settings, report)
        self.task_manager = create_task_manager()
        self.batch_runner = BatchRunner(
            self.task_manager,
            analyzer=self.media_analyzer,
            speech_engine=self.speech_engine,
            ocr_engine=self.ocr_engine,
            translation_engine=self.translation_engine,
            quality_engine=self.quality_engine,
            device=str(settings.get("batch.device") or settings.get("hardware.device") or "auto"),
            prefer_gpu=bool(settings.get("batch.prefer_gpu", settings.get("hardware.prefer_gpu", True))),
            max_concurrent=int(settings.get("batch.max_concurrent", 1) or 1),
            ram_limit_gb=float(settings.get("batch.ram_limit_gb", 0) or 0),
            min_free_ram_gb=float(settings.get("batch.min_free_ram_gb", 1.5) or 1.5),
            cpu_threads=int(settings.get("batch.cpu_threads", settings.get("hardware.cpu_threads", 0)) or 0),
            source_lang="auto",
            target_lang=str(settings.get("app.target_language", "zh-CN") or "zh-CN"),
        )
        self._transcribe_worker: TranscribeWorker | None = None
        self._translate_after_speech = False
        self._speech_ready_for_translate = False
        self._ocr_worker: OCRWorker | None = None
        self._translate_worker: TranslateWorker | None = None
        self._speaker_worker: SpeakerWorker | None = None
        self._inpaint_worker: InpaintWorker | None = None
        self._waveform_worker: WaveformWorker | None = None
        self._realtime_worker: RealtimeWorker | None = None
        self._batch_worker: BatchWorker | None = None
        self._model_worker: ModelWorker | None = None
        self._export_worker: ExportWorker | None = None
        self._realtime_active = False
        self._realtime_cues: list = []
        self._realtime_cursor = 0
        self._realtime_last_process_ms: int | None = None
        self._realtime_last_pos = 0
        self._find_dialog: FindReplaceDialog | None = None
        self._ocr_region: NormalizedRegion | None = None
        self._recovery = RecoveryJournal()
        self._project_dirty = False
        self._last_analysis = None
        self._last_speech: dict[str, Any] = {}
        self._last_ocr: dict[str, Any] = {}
        self.setObjectName("mainWindow")
        self.setWindowTitle(strings.APP_TITLE)
        self.setAcceptDrops(True)
        self.setMinimumSize(1024, 680)
        self.resize(1280, 800)
        self._build()
        self._apply_hardware_display()
        self._load_settings_into_controls()
        self._restore_layout()
        self._refresh_project_views()
        self.refresh_models()
        self._update_status()
        if os.environ.get("LOCALVIDEOAI_SKIP_RECOVERY") != "1":
            self._recovery.mark_open(self._project_path)
        self._start_autosave_timer()

    def current_page_id(self) -> str:
        return self._current_page

    def project_path(self) -> Path | None:
        return self._project_path

    def project_data(self) -> dict[str, Any]:
        return self._project

    def menu_titles(self) -> list[str]:
        return [action.text().replace("&", "") for action in self.menuBar().actions()]

    def page_titles(self) -> list[str]:
        return [title for _, title in PAGES]

    def switch_page(self, page_id: str) -> None:
        if page_id not in self._page_index:
            raise KeyError(f"Unknown page: {page_id}")
        self._current_page = page_id
        self.page_stack.setCurrentIndex(self._page_index[page_id])
        for action in self._page_actions.values():
            action.setChecked(action.data() == page_id)
        self._settings.set("ui.last_page", page_id)
        self._apply_editor_layout(page_id)
        self._update_status()

    def add_video_path(self, path: Path) -> None:
        self._append_media("videos", path)
        self._play_video(path)

    def _play_video(self, path: Path, *, autoplay: bool = True, position_ms: int | None = None) -> None:
        self.switch_page("workspace")
        self.video_stage.show_media(str(path))
        self.side_panel.show_media_tab()
        analysis_error = self._analyze_video(path)
        if analysis_error:
            self.timeline.set_media_ready(False, analysis_error)
            self.video_stage.show_placeholder_message(analysis_error)
            self._set_status(analysis_error)
            return
        try:
            self.playback.open(path, autoplay=autoplay)
            if position_ms is not None:
                self.playback.seek_ms(int(position_ms))
            self.timeline.set_media_ready(True)
            self._load_waveform(path)
            self._set_status(f"正在播放：{path.name}")
        except MediaError as exc:
            self.timeline.set_media_ready(False, str(exc))
            self.video_stage.show_placeholder_message(str(exc))
            self._set_status(str(exc))
            self._logger.warning("Cannot play %s: %s", path, exc)

    def _analyze_video(self, path: Path) -> str | None:
        try:
            analysis = self.media_analyzer.analyze(path)
            self._last_analysis = analysis
            self._store_video_info(path, analysis)
            self.side_panel.media_info.set_analysis(analysis)
        except MediaError as exc:
            self.side_panel.media_info.set_error(str(exc))
            self.subtitle_page.set_embedded_tracks(None, [])
            self.side_panel.set_embedded_summary([])
            self._logger.warning("Cannot analyze %s: %s", path, exc)
            return str(exc)
        try:
            tracks = self.subtitle_engine.list_embedded_tracks(path)
        except SubtitleError as exc:
            self._logger.warning("Cannot list embedded subtitles %s: %s", path, exc)
            tracks = []
        self.subtitle_page.set_embedded_tracks(path, tracks)
        self.side_panel.set_embedded_summary([item.label() for item in tracks])
        if analysis.has_embedded_subtitles:
            self._set_status(
                f"媒体分析完成：内嵌字幕 {len(analysis.subtitle_tracks)} 条，音频 {len(analysis.audio_tracks)} 条"
            )
        return None

    def add_subtitle_path(self, path: Path) -> None:
        self._append_media("subtitles", path)
        self._open_subtitle(path)

    def _open_subtitle(self, path: Path) -> None:
        self.switch_page("subtitles")
        try:
            document = self.subtitle_engine.load_document(path)
            self.subtitle_page.set_document(document)
            warning = f"，警告 {len(document.warnings)} 条" if document.warnings else ""
            self._set_status(f"已导入字幕：{path.name}（{len(document.segments)} 条{warning}）")
        except SubtitleError as exc:
            self.subtitle_page.clear()
            self.subtitle_page.hint.setText(str(exc))
            self._set_status(str(exc))
            self._logger.warning("Cannot load subtitle %s: %s", path, exc)

    def save_subtitle(self) -> Path | None:
        document = self.subtitle_page.document
        if document is None:
            self._set_status("没有打开的字幕")
            return None
        if document.source_path is None:
            return self.save_subtitle_as()
        path = self.subtitle_engine.save_document(document, document.source_path, document.format_name)
        self.subtitle_page.set_document(document, reset_history=False)
        self._set_status(f"字幕已保存：{path}")
        return path

    def save_subtitle_as(self) -> Path | None:
        document = self.subtitle_page.document
        if document is None:
            self._set_status("没有打开的字幕")
            return None
        path, _ = QFileDialog.getSaveFileName(self, "字幕另存为", "", SUBTITLE_FILTER)
        if not path:
            return None
        destination = Path(path)
        fmt = destination.suffix.lstrip(".").lower() or "srt"
        saved = self.subtitle_engine.save_document(document, destination, fmt)
        self._append_media("subtitles", saved)
        self.subtitle_page.set_document(document, reset_history=False)
        self._set_status(f"字幕已另存为：{saved}")
        return saved

    def export_media(self, output: Path | None = None, **options) -> None:
        video = self.playback.source_path or Path(str(self._project.get("current_video") or ""))
        if not video or not Path(video).is_file():
            QMessageBox.information(self, strings.EXPORT, "请先打开视频再导出。")
            return
        document = self.subtitle_page.document
        subtitle_path = document.source_path if document is not None else None
        if output is None and not options:
            default_dir = str(self._settings.get("export.output_dir") or Path(video).parent)
            dialog = ExportDialog(self, default_dir=default_dir)
            self._set_combo(dialog.format_combo, self._settings.get("export.format", "srt"))
            self._set_combo(dialog.container_combo, self._settings.get("export.container", "mp4"))
            self._set_combo(dialog.codec_combo, self._settings.get("export.video_codec", "copy"))
            if self.settings_page.export_burn_in.isChecked():
                self._set_combo(dialog.mode_combo, "burn_in")
            else:
                self._set_combo(dialog.mode_combo, self._settings.get("export.mode", "embed"))
            if dialog.exec() != dialog.DialogCode.Accepted:
                return
            values = dialog.values()
            if not values["output"]:
                QMessageBox.information(self, strings.EXPORT, "请选择输出路径。")
                return
            output = Path(values["output"])
            options = values
        if output is None:
            QMessageBox.information(self, strings.EXPORT, "请选择输出路径。")
            return
        mode = str(
            options.get("mode")
            or ("burn_in" if self.settings_page.export_burn_in.isChecked() else self._settings.get("export.mode", "embed"))
            or "embed"
        )
        request = ExportRequest(
            video_path=Path(video),
            subtitle_path=subtitle_path,
            output_path=Path(output),
            burn_in=mode == "burn_in",
            mode=mode,
            container=str(options.get("container") or self.settings_page.export_container.currentData() or "mp4"),
            video_codec=str(options.get("video_codec") or self.settings_page.export_codec.currentData() or "copy"),
            subtitle_format=str(options.get("subtitle_format") or self.settings_page.export_format.currentData() or "srt"),
            picture_changed=mode == "burn_in",
            project_payload=self.capture_project_state() if mode == "project" else None,
        )
        self._settings.set("export.format", request.subtitle_format)
        self._settings.set("export.container", request.container)
        self._settings.set("export.video_codec", request.video_codec)
        self._settings.set("export.mode", request.mode)
        self._settings.set("export.burn_in", request.burn_in)
        self._settings.set("export.output_dir", str(Path(output).parent))
        self._start_export_job(request)

    def _start_export_job(self, request: ExportRequest) -> None:
        if self._export_worker is not None and self._export_worker.isRunning():
            QMessageBox.information(self, strings.EXPORT, "已有导出任务在运行。")
            return
        if not self._begin_heavy_job("导出"):
            return
        self._set_status("正在导出…")
        worker = ExportWorker(self.export_engine, request, self)
        worker.progressChanged.connect(self._on_export_progress)
        worker.succeeded.connect(self._on_export_ok)
        worker.failed.connect(self._on_export_fail)
        worker.finished.connect(lambda: self._end_heavy_job("导出"))
        self._export_worker = worker
        worker.start()

    def _on_export_progress(self, current: int, total: int, message: str) -> None:
        self._set_status(f"导出 {current}/{total} {message[:80]}")

    def _on_export_ok(self, result: object) -> None:
        path = getattr(result, "output_path", result)
        notes = getattr(result, "notes", [])
        extra = f"；{notes[0]}" if notes else ""
        self._set_status(f"导出完成：{path}{extra}")

    def _on_export_fail(self, message: str) -> None:
        QMessageBox.warning(self, strings.EXPORT, message)
        self._set_status(message)

    def preview_embedded_subtitle(self):
        track = self.subtitle_page.selected_embedded_track()
        video = self.subtitle_page.embedded_video_path
        if track is None or video is None:
            message = "没有可预览的内嵌字幕轨道"
            self.subtitle_page.show_extract_error(message)
            self._set_status(message)
            return None
        try:
            document = self.subtitle_engine.preview_embedded(video, track.index)
        except SubtitleError as exc:
            self._on_embedded_subtitle_error(str(exc))
            return None
        self.switch_page("subtitles")
        self.subtitle_page.show_preview(document, track)
        self._set_status(
            f"已预览内嵌字幕：轨道 #{track.index}，{len(document.segments)} 条，"
            f"语言 {document.detected_language or track.language}"
        )
        return document

    def extract_embedded_subtitle(self):
        track = self.subtitle_page.selected_embedded_track()
        video = self.subtitle_page.embedded_video_path
        if track is None or video is None:
            message = "没有可提取的内嵌字幕轨道"
            self.subtitle_page.show_extract_error(message)
            self._set_status(message)
            return None
        try:
            document = self.subtitle_engine.extract_embedded_document(video, track.index)
        except SubtitleError as exc:
            self._on_embedded_subtitle_error(str(exc))
            return None
        self.switch_page("subtitles")
        self.subtitle_page.set_document(document)
        self._set_status(
            f"已提取内嵌字幕：轨道 #{track.index}，{len(document.segments)} 条，"
            f"已转为内部格式 SubtitleSegment，语言 {document.detected_language or track.language}"
        )
        return document

    def _on_embedded_subtitle_error(self, message: str) -> None:
        self.subtitle_page.show_extract_error(message)
        self._set_status(message)
        self._logger.warning("%s", message)

    def current_media_path(self) -> Path | None:
        if self.playback.source_path is not None:
            return self.playback.source_path
        videos = self._project.get("videos") or []
        if videos and videos[0].get("path"):
            return Path(str(videos[0]["path"]))
        return None

    def start_transcription(self) -> None:
        path = self.current_media_path()
        if path is None:
            self._set_status("请先打开视频再开始语音识别")
            return
        if self._realtime_active:
            self._set_status("请先停止实时翻译再开始整段语音识别")
            return
        if self._transcribe_worker is not None and self._transcribe_worker.isRunning():
            self._set_status("语音识别正在进行")
            return
        if not self._begin_heavy_job("语音识别"):
            return
        language = self.side_panel.source_language_combo.currentData()
        device = str(self.side_panel.device_combo.currentData() or "auto")
        prefer_gpu = bool(self._settings.get("hardware.prefer_gpu", True))
        self.side_panel.transcribe_button.setEnabled(False)
        worker = TranscribeWorker(
            self.speech_engine,
            path,
            None if language in {None, "auto"} else str(language),
            device,
            prefer_gpu,
            self,
            chunk_ms=self._perf.policy.chunk_ms,
            overlap_ms=self._perf.policy.overlap_ms,
            progress_min_interval_ms=self._perf.policy.progress_min_interval_ms,
        )
        worker.progressChanged.connect(self._on_transcribe_progress)
        worker.succeeded.connect(self._on_transcribe_ok)
        worker.failed.connect(self._on_transcribe_fail)
        worker.finished.connect(self._on_transcribe_finished)
        self._transcribe_worker = worker
        worker.start()
        self._set_status(f"正在本地识别：{path.name}")

    def transcribe_current_media(self):
        """Synchronous recognition for tests. Same engine as the UI button."""
        path = self.current_media_path()
        if path is None:
            raise FileNotFoundError("请先打开视频再开始语音识别")
        language = self.side_panel.source_language_combo.currentData()
        device = str(self.side_panel.device_combo.currentData() or "auto")
        prefer_gpu = bool(self._settings.get("hardware.prefer_gpu", True))
        transcript = self.speech_engine.transcribe_media(
            path,
            language=None if language in {None, "auto"} else str(language),
            device_preference=device,
            prefer_gpu=prefer_gpu,
        )
        self._apply_transcript(transcript)
        return transcript

    def _on_transcribe_progress(self, current_ms: int, total_ms: int, message: str) -> None:
        percent = int((current_ms / total_ms) * 100) if total_ms else 0
        self._set_status(f"识别进度 {percent}%  {message}")

    def _on_transcribe_ok(self, transcript) -> None:
        self._apply_transcript(transcript)

    def _apply_transcript(self, transcript) -> None:
        document = preserve_locked(self.subtitle_page.document, transcript_to_document(transcript))
        document.quality_stage = "recognize"
        report = self._inspect_quality(document, apply_fixes=True)
        self.switch_page("subtitles")
        self.subtitle_page.set_document(document)
        self.subtitle_page.apply_quality_report(report)
        self._last_speech = {
            "language": transcript.language,
            "model_id": transcript.model_id,
            "device": transcript.device,
        }
        if transcript.model_id:
            try:
                self.model_manager.set_active("speech", f"speech/{transcript.model_id}")
            except Exception:
                self.model_manager._active["speech"] = f"speech/{transcript.model_id}"
        self._mark_project_dirty()
        self._speech_ready_for_translate = True
        raw = f" 原始结果已保存：{transcript.raw_path}" if transcript.raw_path else ""
        pending = " 识别完成后将按目标语言翻译。" if self._translate_after_speech else ""
        self._set_status(
            f"识别完成：{len(transcript.segments)} 句，语言 {transcript.language}，"
            f"模型 {transcript.model_id}/{transcript.device}。已纠错并 QA。"
            f"{raw}{pending}".strip()
        )
        self._show_document_caption(self.playback.position_ms())

    def _on_transcribe_fail(self, message: str) -> None:
        self._speech_ready_for_translate = False
        if self._translate_after_speech:
            self._translate_after_speech = False
            message = f"{message}。识别未完成，没有按目标语言翻译。"
        self.subtitle_page.hint.setText(message)
        self._set_status(message)
        self._logger.warning("%s", message)

    def _on_transcribe_finished(self) -> None:
        self.side_panel.transcribe_button.setEnabled(True)
        self._end_heavy_job("语音识别")
        if self._translate_after_speech and self._speech_ready_for_translate:
            self._translate_after_speech = False
            self._speech_ready_for_translate = False
            self.start_translation()

    def toggle_realtime(self) -> None:
        if self._realtime_active:
            self.stop_realtime()
            return
        self.start_realtime()

    def start_realtime(self) -> None:
        path = self.current_media_path()
        if path is None:
            self._set_status("请先打开视频再开始实时翻译")
            return
        if self._transcribe_worker is not None and self._transcribe_worker.isRunning():
            self._set_status("整段语音识别进行中，无法同时开实时翻译")
            return
        if self._translate_worker is not None and self._translate_worker.isRunning():
            self._set_status("整段翻译进行中，无法同时开实时翻译")
            return
        if self._ocr_worker is not None and self._ocr_worker.isRunning():
            self._set_status("硬字幕 OCR 进行中，无法同时开实时翻译")
            return
        if not self._begin_heavy_job("实时翻译"):
            return
        self._realtime_active = True
        self._realtime_cues = []
        self._realtime_cursor = max(0, self.playback.position_ms())
        self._realtime_last_process_ms = None
        self._realtime_last_pos = self.playback.position_ms()
        self.side_panel.realtime_button.setText(strings.STOP_REALTIME)
        action = self.findChild(QAction, "action_menuRealtime")
        if action is not None:
            action.setText(strings.STOP_REALTIME)
        self.video_stage.set_realtime_active(True)
        self._update_realtime_actual_label()
        if self.playback.source_path is not None and self.playback.state_name() != "playing":
            self.playback.play()
        self._set_status("实时翻译已开始：后台识别+翻译，播放不中断")
        self._tick_realtime()

    def stop_realtime(self) -> None:
        self._realtime_active = False
        self._stop_realtime_worker()
        self.side_panel.realtime_button.setText(strings.START_REALTIME)
        action = self.findChild(QAction, "action_menuRealtime")
        if action is not None:
            action.setText(strings.START_REALTIME)
        self.video_stage.set_realtime_active(False)
        self._set_status("实时翻译已停止")
        self._end_heavy_job("实时翻译")

    def _stop_realtime_worker(self, timeout_ms: int = 8000) -> None:
        worker = self._realtime_worker
        if worker is None:
            return
        if worker.isRunning():
            worker.requestInterruption()
            worker.wait(timeout_ms)
        self._realtime_worker = None

    def _realtime_options(self) -> tuple[int, str, str, str, str, bool]:
        requested = normalize_delay_ms(int(self.side_panel.realtime_delay_combo.currentData() or 3000))
        profile = normalize_profile(str(self.side_panel.realtime_profile_combo.currentData() or "balanced"))
        source = str(self.side_panel.source_language_combo.currentData() or "auto")
        target = normalize_translation_language(str(self.side_panel.language_combo.currentData() or "zh")) or "zh"
        device = str(self.side_panel.device_combo.currentData() or "auto")
        prefer_gpu = bool(self._settings.get("hardware.prefer_gpu", True))
        return requested, profile, source, target, device, prefer_gpu

    def _update_realtime_actual_label(self) -> None:
        requested, profile, *_ = self._realtime_options()
        window = adjust_window_ms(requested, profile, self._realtime_last_process_ms)
        self.side_panel.realtime_actual_label.setText(
            f"实际窗口：{window / 1000:.1f} 秒（目标 {requested / 1000:.0f} 秒 / {profile_settings(profile).label}）"
        )

    def _tick_realtime(self) -> None:
        if not self._realtime_active:
            return
        if self._realtime_worker is not None and self._realtime_worker.isRunning():
            return
        path = self.current_media_path()
        if path is None:
            self._set_status("实时翻译：没有打开的视频")
            return
        duration = self.playback.duration_ms()
        if duration <= 0:
            try:
                duration = self.media_analyzer.analyze(path).duration_ms
            except MediaError:
                duration = 0
        if duration <= 0:
            return
        requested, profile, source, target, device, prefer_gpu = self._realtime_options()
        window = adjust_window_ms(requested, profile, self._realtime_last_process_ms)
        overlap = profile_settings(profile).overlap_ms
        start = min(self._realtime_cursor, max(0, duration - 50))
        if start >= duration:
            self._set_status("实时翻译已处理到视频结尾")
            return
        playhead = self.playback.position_ms()
        if start > playhead + window:
            return
        self._update_realtime_actual_label()
        worker = RealtimeWorker(
            self.speech_engine,
            self.translation_engine,
            path,
            start,
            requested,
            source,
            target,
            profile,
            device,
            prefer_gpu,
            self._realtime_last_process_ms,
            duration,
            self,
        )
        worker.succeeded.connect(self._on_realtime_ok)
        worker.failed.connect(self._on_realtime_fail)
        worker.finished.connect(self._on_realtime_finished)
        self._realtime_worker = worker
        worker.start()
        self._set_status(f"实时处理 {start / 1000:.1f}–{(start + window) / 1000:.1f} 秒，窗口 {window / 1000:.1f} 秒")
        self._realtime_pending_overlap = overlap

    def _on_realtime_ok(self, cue) -> None:
        self._realtime_cues.append(cue)
        overlap = int(getattr(self, "_realtime_pending_overlap", 300))
        self._realtime_cursor = max(cue.end_ms - overlap, cue.start_ms + 50)
        self._realtime_last_process_ms = cue.process_ms
        self._update_realtime_actual_label()
        self._show_realtime_caption(self.playback.position_ms())
        text = cue.display_text()
        if text:
            self._set_status(
                f"实时字幕 {cue.start_ms / 1000:.1f}s  耗时 {cue.process_ms} ms  {cue.model_id}/{cue.speech_device}"
            )

    def _on_realtime_fail(self, message: str) -> None:
        requested, profile, *_ = self._realtime_options()
        window = adjust_window_ms(requested, profile, self._realtime_last_process_ms)
        self._realtime_cursor += max(window, 1000)
        self._set_status(message)
        self._logger.warning("%s", message)

    def _on_realtime_finished(self) -> None:
        self._realtime_worker = None
        if self._realtime_active:
            self._tick_realtime()

    def _show_realtime_caption(self, position_ms: int) -> None:
        text = ""
        for cue in reversed(self._realtime_cues):
            if cue.start_ms - 250 <= position_ms <= cue.end_ms + 600:
                text = cue.display_text()
                if text:
                    break
        if not text and self._realtime_cues:
            text = self._realtime_cues[-1].display_text()
        self.video_stage.set_realtime_caption(text)

    def _show_document_caption(self, position_ms: int) -> None:
        if self._realtime_active:
            return
        document = self.subtitle_page.document
        text = ""
        if document is not None:
            for segment in document.segments:
                if segment.start_time - 80 <= position_ms <= segment.end_time + 80:
                    translated = (segment.translated_text or "").strip()
                    text = translated or segment.display_text()
                    break
        self.video_stage.set_realtime_caption(text)

    def _on_realtime_position(self, position_ms: int) -> None:
        if not self._realtime_active:
            self._show_document_caption(position_ms)
            return
        last = self._realtime_last_pos
        if abs(position_ms - last) > 2500:
            self._realtime_cursor = max(0, position_ms)
        self._realtime_last_pos = position_ms
        self._show_realtime_caption(position_ms)
        self._tick_realtime()

    def start_ocr(self) -> None:
        path = self.current_media_path()
        if path is None:
            self._set_status("请先打开视频再开始硬字幕 OCR")
            return
        if self._realtime_active:
            self._set_status("请先停止实时翻译再开始硬字幕 OCR")
            return
        if self._ocr_worker is not None and self._ocr_worker.isRunning():
            self._set_status("硬字幕 OCR 正在进行")
            return
        region = self._current_ocr_region()
        if self.side_panel.ocr_region_combo.currentData() == "manual" and region is None:
            self._set_status("请先框选字幕区域")
            return
        if not self._begin_heavy_job("硬字幕OCR"):
            return
        language = self.side_panel.source_language_combo.currentData()
        device = str(self.side_panel.device_combo.currentData() or "auto")
        prefer_gpu = bool(self._settings.get("hardware.prefer_gpu", True))
        self.side_panel.ocr_button.setEnabled(False)
        worker = OCRWorker(
            self.ocr_engine,
            path,
            None if language in {None, "auto"} else str(language),
            region,
            device,
            prefer_gpu,
            self,
            sample_fps=self._perf.policy.ocr_sample_fps,
            progress_min_interval_ms=self._perf.policy.progress_min_interval_ms,
        )
        worker.progressChanged.connect(self._on_ocr_progress)
        worker.succeeded.connect(self._on_ocr_ok)
        worker.failed.connect(self._on_ocr_fail)
        worker.finished.connect(self._on_ocr_finished)
        self._ocr_worker = worker
        worker.start()
        self._set_status(f"正在本地 OCR：{path.name}")

    def ocr_current_media(self):
        """Synchronous OCR for tests. Same engine as the UI button."""
        path = self.current_media_path()
        if path is None:
            raise FileNotFoundError("请先打开视频再开始硬字幕 OCR")
        language = self.side_panel.source_language_combo.currentData()
        device = str(self.side_panel.device_combo.currentData() or "auto")
        prefer_gpu = bool(self._settings.get("hardware.prefer_gpu", True))
        transcript = self.ocr_engine.recognize_video(
            path,
            language=None if language in {None, "auto"} else str(language),
            region=self._current_ocr_region(),
            device_preference=device,
            prefer_gpu=prefer_gpu,
        )
        self._apply_ocr_transcript(transcript)
        return transcript

    def pick_ocr_region(self) -> NormalizedRegion | None:
        path = self.current_media_path()
        if path is None:
            self._set_status("请先打开视频再框选字幕区域")
            return None
        still = logs_dir() / "ocr-region-preview.jpg"
        try:
            position = int(self.playback.position_ms() or 1000)
            extract_still(path, still, time_ms=max(position, 400))
        except (MediaError, Exception) as exc:
            self._set_status(f"无法截取预览帧：{exc}")
            return None
        dialog = RegionPickerDialog(still, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        region = dialog.region()
        if region is None:
            self._set_status("没有框选有效区域")
            return None
        self._ocr_region = region
        self.side_panel.ocr_region_combo.setCurrentIndex(1)
        self._set_status(f"已框选字幕区域 x={region.x:.2f} y={region.y:.2f}")
        return region

    def _current_ocr_region(self) -> NormalizedRegion | None:
        if self.side_panel.ocr_region_combo.currentData() == "manual":
            return self._ocr_region
        return None

    def _on_ocr_progress(self, current_ms: int, total_ms: int, message: str) -> None:
        percent = int((current_ms / total_ms) * 100) if total_ms else 0
        self._set_status(f"OCR 进度 {percent}%  {message}")

    def _on_ocr_ok(self, transcript) -> None:
        self._apply_ocr_transcript(transcript)

    def _apply_ocr_transcript(self, transcript) -> None:
        document = preserve_locked(self.subtitle_page.document, ocr_to_document(transcript))
        document.quality_stage = "recognize"
        report = self._inspect_quality(document, apply_fixes=True)
        self.switch_page("subtitles")
        self.subtitle_page.set_document(document)
        self.subtitle_page.apply_quality_report(report)
        self._last_ocr = {
            "language": transcript.language,
            "model_id": transcript.model_id,
            "device": transcript.device,
            "region": list(transcript.region),
            "region_source": transcript.region_source,
        }
        if transcript.model_id:
            self.model_manager._active["ocr"] = f"ocr/{transcript.model_id}"
        self._mark_project_dirty()
        raw = f" 原始结果已保存：{transcript.raw_path}" if transcript.raw_path else ""
        self._set_status(
            f"OCR 完成：{len(transcript.cues)} 条，语言 {transcript.language}，"
            f"抽帧 {transcript.frames_decoded}，实际 OCR {transcript.frames_ocr}。已纠错并 QA。"
            f"{raw}".strip()
        )

    def _on_ocr_fail(self, message: str) -> None:
        self.subtitle_page.hint.setText(message)
        self._set_status(message)
        self._logger.warning("%s", message)

    def _on_ocr_finished(self) -> None:
        self.side_panel.ocr_button.setEnabled(True)
        self._end_heavy_job("硬字幕OCR")

    def start_hardsub(self) -> None:
        path = self.current_media_path()
        if path is None:
            self._set_status("请先打开带硬字幕的视频")
            return
        if self._inpaint_worker is not None and self._inpaint_worker.isRunning():
            self._set_status("硬字幕处理正在进行")
            return
        if not self._begin_heavy_job("硬字幕处理"):
            return
        mode = str(self.side_panel.hardsub_mode_combo.currentData() or "smart")
        dest = path.with_name(f"{path.stem}.hardsub_{mode}.mp4")
        language = self.side_panel.source_language_combo.currentData()
        self.side_panel.hardsub_button.setEnabled(False)
        worker = InpaintWorker(
            self.inpaint_engine,
            path,
            dest,
            mode,
            self.subtitle_page.document,
            None if language in {None, "auto"} else str(language),
            self._current_ocr_region(),
            self,
        )
        worker.progressChanged.connect(self._on_hardsub_progress)
        worker.succeeded.connect(self._on_hardsub_ok)
        worker.failed.connect(self._on_hardsub_fail)
        worker.finished.connect(self._on_hardsub_finished)
        self._inpaint_worker = worker
        worker.start()
        self._set_status(f"正在本地处理硬字幕（{self.side_panel.hardsub_mode_combo.currentText()}）…")

    def process_hardsub_current(self, destination: Path, mode: str = "smart"):
        """Synchronous hard-sub processing for tests. Same engine as the UI button."""
        path = self.current_media_path()
        if path is None:
            raise FileNotFoundError("请先打开带硬字幕的视频")
        language = self.side_panel.source_language_combo.currentData()
        return self.inpaint_engine.process_video(
            path,
            destination,
            mode=mode,
            document=self.subtitle_page.document,
            language=None if language in {None, "auto"} else str(language),
            region=self._current_ocr_region(),
        )

    def _on_hardsub_progress(self, current: int, total: int, message: str) -> None:
        percent = int((current / total) * 100) if total else 0
        self._set_status(f"硬字幕处理 {percent}%  {message}")

    def _on_hardsub_ok(self, result) -> None:
        if result.subtitle_path and Path(result.subtitle_path).is_file():
            try:
                self.add_subtitle_path(Path(result.subtitle_path))
            except Exception:
                pass
        note = result.reason or ""
        if result.mode_used != result.mode_requested:
            note = f"已自动改为{result.mode_used}。{note}"
        if result.recommended_mode == "overlay" and result.mode_requested == "smart":
            note = f"自动建议：覆盖模式。{note}"
        compare = f" 对比图：{result.comparison_path}" if result.comparison_path else ""
        self._set_status(
            f"硬字幕处理完成：{result.output_path.name}（{result.mode_used}，{result.frames_processed} 帧）。{note}{compare}".strip()
        )
        if result.output_path.is_file():
            self.add_video_path(result.output_path)

    def _on_hardsub_fail(self, message: str) -> None:
        self._set_status(message)
        self._logger.warning("%s", message)

    def _on_hardsub_finished(self) -> None:
        self.side_panel.hardsub_button.setEnabled(True)
        self._end_heavy_job("硬字幕处理")

    def start_translation(self) -> None:
        if self._transcribe_worker is not None and self._transcribe_worker.isRunning():
            self._translate_after_speech = True
            target = self.side_panel.language_combo.currentText() or "目标语言"
            self._set_status(f"语音识别还在进行。识别完成后会翻译成{target}")
            return
        document = self.subtitle_page.document
        if document is None or not document.segments:
            self._set_status("请先导入字幕、语音识别或硬字幕 OCR")
            return
        if self._realtime_active:
            self._set_status("请先停止实时翻译再开始整段翻译")
            return
        if self._translate_worker is not None and self._translate_worker.isRunning():
            self._set_status("翻译正在进行")
            return
        if not self._begin_heavy_job("翻译"):
            return
        source, targets, quality, device, prefer_gpu = self._translation_options()
        self.side_panel.translate_button.setEnabled(False)
        worker = TranslateWorker(
            self.translation_engine,
            document,
            source,
            targets,
            quality,
            device,
            prefer_gpu,
            self,
        )
        worker.progressChanged.connect(self._on_translate_progress)
        worker.succeeded.connect(self._on_translate_ok)
        worker.failed.connect(self._on_translate_fail)
        worker.finished.connect(self._on_translate_finished)
        self._translate_worker = worker
        worker.start()
        from localvideoai.translation.context import context_hint_for

        self._set_status(f"正在本地翻译 → {', '.join(targets)}（{quality}，{context_hint_for(quality)}）")

    def translate_current_document(self):
        """Synchronous translation for tests. Same engine as the UI button."""
        document = self.subtitle_page.document
        if document is None or not document.segments:
            raise TranslationError("请先导入字幕、语音识别或硬字幕 OCR")
        source, targets, quality, device, prefer_gpu = self._translation_options()
        results = self.translation_engine.translate_document(
            document,
            source,
            targets,
            quality=quality,
            device_preference=device,
            prefer_gpu=prefer_gpu,
        )
        self._apply_translation(document, results)
        return document

    def start_diarization(self) -> None:
        document = self.subtitle_page.document
        path = self.current_media_path()
        if document is None or not document.segments:
            self._set_status("请先导入字幕或完成语音识别，再做说话人分离")
            return
        if path is None:
            self._set_status("请先打开视频或音频，再做说话人分离")
            return
        if self._speaker_worker is not None and self._speaker_worker.isRunning():
            self._set_status("说话人分离正在进行")
            return
        if not self._begin_heavy_job("说话人分离"):
            return
        self.side_panel.diarize_button.setEnabled(False)
        worker = SpeakerWorker(self.speaker_engine, document, path, self)
        worker.progressChanged.connect(self._on_speaker_progress)
        worker.succeeded.connect(self._on_speaker_ok)
        worker.failed.connect(self._on_speaker_fail)
        worker.finished.connect(self._on_speaker_finished)
        self._speaker_worker = worker
        worker.start()
        self._set_status("正在本机分离说话人…")

    def edit_speaker_map(self) -> None:
        document = self.subtitle_page.document
        if document is None or not document.segments:
            self._set_status("请先有字幕再编辑人物映射")
            return
        dialog = SpeakerMapDialog(document, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        dialog.apply_to_document()
        self.subtitle_page.set_document(document, reset_history=False)
        self._set_status("已更新人物映射。保存字幕后重新打开仍然存在。")

    def _on_speaker_progress(self, current: int, total: int, message: str) -> None:
        percent = int((current / total) * 100) if total else 0
        self._set_status(f"说话人进度 {percent}%  {message}")

    def _on_speaker_ok(self, result) -> None:
        document = self.subtitle_page.document
        if document is not None:
            self.subtitle_page.set_document(document, reset_history=False)
        if getattr(result, "fallback", False):
            reason = getattr(result, "fallback_reason", "") or "已保持普通字幕"
            self._set_status(reason)
            return
        names = "、".join(result.speaker_ids) if getattr(result, "speaker_ids", ()) else "Speaker"
        self._set_status(f"说话人分离完成：{names}。可用「人物映射」改成真实姓名。")

    def _on_speaker_fail(self, message: str) -> None:
        self._set_status(message)
        self._logger.warning("%s", message)

    def _on_speaker_finished(self) -> None:
        self.side_panel.diarize_button.setEnabled(True)
        self._end_heavy_job("说话人分离")

    def run_quality_check(self) -> None:
        document = self.subtitle_page.document
        if document is None or not document.segments:
            self._set_status("请先导入字幕、语音识别或硬字幕 OCR")
            return
        report = self._inspect_quality(document, apply_fixes=True)
        self.switch_page("subtitles")
        self.subtitle_page.set_document(document, reset_history=False)
        self.subtitle_page.apply_quality_report(report)
        self._set_status(
            f"QA 完成：文档综合 {report.document_score}，{report.issue_count} 个问题，"
            f"{len(report.below_90)} 条低于 90。绿色高质量 / 黄色建议检查 / 红色需要人工检查。"
        )

    def jump_quality_issue(self) -> None:
        document = self.subtitle_page.document
        if document is None or not document.segments:
            self._set_status("请先做质量检查")
            return
        if self.subtitle_page.quality_report is None:
            report = self._inspect_quality(document, apply_fixes=False)
            self.subtitle_page.apply_quality_report(report)
        index = self.subtitle_page.next_issue_row()
        if index is None:
            self._set_status("没有低于 90 分或带问题的字幕")
            return
        self.switch_page("subtitles")
        self.subtitle_page.select_row(index)
        self.playback.seek_ms(document.segments[index].start_time)
        payload = document.segments[index].extra.get("qa") if isinstance(document.segments[index].extra, dict) else {}
        score = payload.get("composite") if isinstance(payload, dict) else None
        self._set_status(f"已跳到 #{document.segments[index].id}，综合 {score}")

    def confirm_selected_quality(self) -> None:
        document = self.subtitle_page.document
        if document is None or not document.segments:
            self._set_status("请先选择要确认的字幕")
            return
        indexes = self.subtitle_page.selected_indexes()
        if not indexes:
            self._set_status("请先选择要人工确认的字幕")
            return
        for index in indexes:
            self.quality_engine.confirm_cue(document, index)
        report = self._inspect_quality(document, apply_fixes=False)
        self.subtitle_page.set_document(document, reset_history=False)
        self.subtitle_page.apply_quality_report(report)
        self._set_status(f"已人工确认 {len(indexes)} 条。锁定后 AI 不能覆盖。")

    def lock_confirmed_cues(self) -> None:
        document = self.subtitle_page.document
        if document is None or not document.segments:
            self._set_status("请先做质量检查并人工确认")
            return
        locked = self.quality_engine.lock_confirmed(document)
        report = self._inspect_quality(document, apply_fixes=False)
        self.subtitle_page.set_document(document, reset_history=False)
        self.subtitle_page.apply_quality_report(report)
        if locked:
            self._set_status(f"已锁定 {locked} 条已确认字幕。识别/翻译不会覆盖它们。")
        else:
            self._set_status("没有已确认且未锁定的字幕")

    def set_quality_filter_below_90(self, enabled: bool) -> None:
        self.subtitle_page.set_filter_below_90(enabled)
        self._sync_quality_filter_controls(enabled)
        if enabled:
            self._set_status("已筛选综合评分低于 90 的字幕")
        else:
            self._set_status("已显示全部字幕")

    def _inspect_quality(self, document, *, apply_fixes: bool):
        return self.quality_engine.inspect_document(
            document,
            resources=getattr(self.translation_engine, "_resources", None) or TranslationResources(),
            apply_fixes=apply_fixes,
        )

    def _sync_quality_filter_controls(self, enabled: bool) -> None:
        box = self.side_panel.quality_filter_box
        box.blockSignals(True)
        box.setChecked(enabled)
        box.blockSignals(False)
        action = self.findChild(QAction, "action_menuQualityFilter")
        if action is not None:
            action.blockSignals(True)
            action.setChecked(enabled)
            action.blockSignals(False)
        page_box = self.subtitle_page.filter_below_90
        if page_box.isChecked() != enabled:
            page_box.blockSignals(True)
            page_box.setChecked(enabled)
            page_box.blockSignals(False)
            self.subtitle_page.set_filter_below_90(enabled)

    def _on_quality_issue_activated(self, index: int) -> None:
        document = self.subtitle_page.document
        if document is None or not (0 <= index < len(document.segments)):
            return
        self.playback.seek_ms(document.segments[index].start_time)

    def edit_translation_resources(self) -> None:
        dialog = TranslationResourcesDialog(TranslationResources(), self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.translation_engine = create_translation_engine(self._report)
            self._set_status("已保存翻译词表（用户修改优先）")

    def _translation_options(self) -> tuple[str, list[str], str, str, bool]:
        source = str(self.side_panel.source_language_combo.currentData() or "auto")
        primary = normalize_translation_language(str(self.side_panel.language_combo.currentData() or "zh")) or "zh"
        extras = self.side_panel.extra_target_langs()
        targets = [primary, *[item for item in extras if item != primary]]
        quality = str(self.side_panel.quality_combo.currentData() or "standard")
        device = str(self.side_panel.device_combo.currentData() or "auto")
        prefer_gpu = bool(self._settings.get("hardware.prefer_gpu", True))
        return source, targets, quality, device, prefer_gpu

    def _on_translate_progress(self, current: int, total: int, message: str) -> None:
        percent = int((current / total) * 100) if total else 0
        self._set_status(f"翻译进度 {percent}%  {message}")

    def _on_translate_ok(self, document) -> None:
        self._apply_translation(document, [])

    def _apply_translation(self, document, results) -> None:
        document.quality_stage = "translate"
        report = self._inspect_quality(document, apply_fixes=False)
        self.switch_page("subtitles")
        self.subtitle_page.set_document(document)
        self.subtitle_page.apply_quality_report(report)
        filled = sum(1 for item in document.segments if item.translated_text.strip())
        extra = ""
        if results:
            extra = f" 模型 {results[0].model_id}/{results[0].device}"
        self._set_status(f"翻译完成：{filled} 条有译文。已做翻译审核和 QA。{extra}".strip())
        self._show_document_caption(self.playback.position_ms())

    def _on_translate_fail(self, message: str) -> None:
        self.subtitle_page.hint.setText(message)
        self._set_status(message)
        self._logger.warning("%s", message)

    def _on_translate_finished(self) -> None:
        self.side_panel.translate_button.setEnabled(True)
        self._end_heavy_job("翻译")

    def add_batch_path(self, path: Path) -> None:
        self.batch_runner.add_video(path)
        self._sync_project_from_tasks()
        self.switch_page("batch")
        self._set_status(strings.STATUS_ADDED.format(name=path.name))

    def start_batch(self) -> None:
        if not self._begin_heavy_job("批处理"):
            return
        self._apply_batch_limits()
        self.batch_runner.start()
        self._ensure_batch_worker()
        self._sync_project_from_tasks()
        self._set_status("批量处理已开始")

    def pause_batch(self) -> None:
        self.batch_runner.pause()
        self._sync_project_from_tasks()
        self._set_status("批量处理已暂停")

    def resume_batch(self) -> None:
        self.start_batch()
        self._set_status("批量处理已继续")

    def cancel_batch(self) -> None:
        ids = self.batch_page.selected_task_ids()
        if ids:
            for task_id in ids:
                self.batch_runner.cancel(task_id)
        else:
            self.batch_runner.cancel(None)
        self._sync_project_from_tasks()
        self._end_heavy_job("批处理")
        self._set_status("已取消选中或未完成的批量任务")

    def retry_batch(self) -> None:
        ids = self.batch_page.selected_task_ids()
        if not ids:
            ids = [str(item["id"]) for item in self.task_manager.list_tasks() if item.get("status") == "失败"]
        for task_id in ids:
            self.batch_runner.retry(task_id)
        self._sync_project_from_tasks()
        self._set_status("已将失败任务重新排队")

    def delete_batch_selected(self) -> None:
        ids = self.batch_page.selected_task_ids()
        if not ids:
            self._set_status("没有选中批量任务")
            return
        for task_id in ids:
            self.batch_runner.delete(task_id)
        self._sync_project_from_tasks()
        self._set_status(strings.STATUS_REMOVED.format(name=f"{len(ids)} 个任务"))

    def remove_selected_media(self) -> None:
        kind, path = self.project_list.selected_path()
        if not path:
            self._set_status("没有选中列表项")
            return
        key = "videos" if kind == "video" else "subtitles"
        self._project[key] = [item for item in self._project.get(key, []) if item.get("path") != path]
        current = self.playback.source_path
        if current is not None and current.resolve() == Path(path).resolve():
            self.playback.close()
            self.timeline.set_media_ready(False)
            self.side_panel.media_info.clear()
            self.subtitle_page.set_embedded_tracks(None, [])
            self.side_panel.set_embedded_summary([])
        self._refresh_project_views()
        self.video_stage.show_media(None)
        self._set_status(strings.STATUS_REMOVED.format(name=Path(path).name))

    def new_project(self, name: str, directory: Path) -> Path:
        path = self._projects.create(name, directory)
        self._project = self._projects.load(path)
        self._project_path = path
        self._project_dirty = False
        self._last_analysis = None
        self._last_speech = {}
        self._last_ocr = {}
        self._refresh_project_views()
        self.video_stage.show_media(None)
        self.side_panel.media_info.clear()
        self.subtitle_page.clear()
        self.subtitle_page.set_embedded_tracks(None, [])
        self.side_panel.set_embedded_summary([])
        self._recovery.mark_open(path)
        self.switch_page("projects")
        self._set_status(strings.STATUS_PROJECT_LOADED.format(name=name))
        return path

    def open_project(self, project_file: Path) -> dict[str, Any]:
        data = self._projects.load(project_file)
        self.apply_project_state(data, project_path=project_file)
        self._recovery.mark_open(project_file)
        self._recovery.mark_clean(project_file)
        self._set_status(strings.STATUS_PROJECT_LOADED.format(name=data.get("name", project_file.name)))
        return self._project

    def save_project(self) -> Path:
        if self._project_path is None:
            raise FileNotFoundError("项目尚未选择保存位置")
        payload = self.capture_project_state()
        path = self._projects.save(self._project_path, payload)
        self._project_path = path
        self._project = self._projects.load(path)
        self._project_dirty = False
        self._recovery.mark_clean(path)
        self._refresh_project_views()
        self._set_status(strings.STATUS_PROJECT_SAVED.format(path=path))
        return path

    def save_project_as(self, project_file: Path) -> Path:
        destination = normalize_project_path(project_file)
        payload = self.capture_project_state()
        path = self._projects.save(destination, payload)
        self._project_path = path
        self._project = self._projects.load(path)
        self._project_dirty = False
        self._recovery.mark_clean(path)
        self._refresh_project_views()
        self._set_status(strings.STATUS_PROJECT_SAVED.format(path=path))
        return path

    def save_user_settings(self) -> Path:
        self._capture_settings_from_controls()
        self._persist_layout()
        path = self._settings.save()
        self._set_status(f"{strings.STATUS_SAVED}：{path}")
        return path

    def apply_theme_preference(self, preference: str) -> str:
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication is not running")
        resolved = apply_theme(app, preference)
        self._settings.set("app.theme", preference)
        self.settings_page.theme_combo.blockSignals(True)
        index = self.settings_page.theme_combo.findData(preference)
        if index >= 0:
            self.settings_page.theme_combo.setCurrentIndex(index)
        self.settings_page.theme_combo.blockSignals(False)
        self._set_status(strings.STATUS_THEME.format(theme=preference))
        return resolved

    def refresh_models(self) -> list[str]:
        records = self.model_manager.list_records()
        self.models_page.set_records(
            self.model_manager.models_root(),
            records,
            recommend_reason=self.model_manager.recommend_reason(),
            empty_hint=self.model_manager.empty_hint(),
        )
        if hasattr(self, "settings_page"):
            self.settings_page.models_dir_edit.setText(str(self.model_manager.models_root()))
            self.settings_page.projects_dir_edit.setText(str(self._settings.get("paths.projects_dir") or projects_dir()))
            self.settings_page.cache_dir_edit.setText(str(self._settings.get("paths.cache_dir") or cache_dir()))
        return [record.id for record in records if record.installed]

    def install_selected_model(self) -> None:
        record = self.models_page.selected_record()
        model_id = record.id if record is not None else "speech/tiny"
        self._start_model_job("install", model_id=model_id)

    def import_local_model(self, source: Path | None = None) -> None:
        if source is None:
            picked = QFileDialog.getExistingDirectory(self, "导入已部署模型目录", str(bundled_models_dir()))
            if not picked:
                return
            source = Path(picked)
        self._start_model_job("import", source=source)

    def delete_selected_model(self) -> None:
        record = self.models_page.selected_record()
        if record is None:
            QMessageBox.information(self, "删除模型", "请先选择要删除的模型。")
            return
        answer = QMessageBox.question(
            self,
            "删除模型",
            f"只删除独立模型目录中的「{record.name}」副本，不会删除软件目录里的已部署文件。确定删除？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.model_manager.delete(record.id)
        except ModelError as exc:
            QMessageBox.warning(self, "删除模型", str(exc))
            return
        self.refresh_models()
        self._set_status(f"已删除模型副本：{record.id}")

    def switch_selected_model(self) -> None:
        record = self.models_page.selected_record()
        if record is None or not record.installed:
            QMessageBox.information(self, "切换模型", "请先安装或导入该模型，再切换为当前模型。")
            return
        try:
            self.model_manager.set_active(record.capability, record.id)
        except Exception as exc:
            QMessageBox.warning(self, "切换模型", str(exc))
            return
        self.refresh_models()
        self._set_status(f"已切换为当前模型：{record.id}")

    def enable_selected_model(self) -> None:
        record = self.models_page.selected_record()
        if record is None:
            QMessageBox.information(self, "启用模型", "请先选择要启用的模型。")
            return
        self.model_manager.enable(record.id)
        self.refresh_models()
        self._set_status(f"已启用：{record.id}")

    def disable_selected_model(self) -> None:
        record = self.models_page.selected_record()
        if record is None:
            QMessageBox.information(self, "禁用模型", "请先选择要禁用的模型。")
            return
        self.model_manager.disable(record.id)
        self.refresh_models()
        self._set_status(f"已禁用：{record.id}")

    def change_models_directory(self) -> None:
        picked = QFileDialog.getExistingDirectory(self, "选择独立模型目录", str(self.model_manager.models_root()))
        if not picked:
            return
        try:
            path = self.model_manager.set_models_root(Path(picked))
        except PathError as exc:
            QMessageBox.warning(self, "模型目录", str(exc))
            return
        self.refresh_models()
        self._set_status(f"模型目录已改为：{path}")

    def change_projects_directory(self) -> None:
        picked = QFileDialog.getExistingDirectory(self, "选择项目目录", str(projects_dir()))
        if not picked:
            return
        path = set_projects_dir(Path(picked))
        self._settings.set("paths.projects_dir", str(path))
        self.settings_page.projects_dir_edit.setText(str(path))
        self._set_status(f"项目目录已改为：{path}")

    def change_cache_directory(self) -> None:
        picked = QFileDialog.getExistingDirectory(self, "选择缓存目录", str(cache_dir()))
        if not picked:
            return
        path = set_cache_dir(Path(picked))
        self._settings.set("paths.cache_dir", str(path))
        self.settings_page.cache_dir_edit.setText(str(path))
        self._set_status(f"缓存目录已改为：{path}")

    def _start_model_job(self, action: str, model_id: str | None = None, source: Path | None = None) -> None:
        if self._model_worker is not None and self._model_worker.isRunning():
            QMessageBox.information(self, "模型", "已有模型任务在运行。")
            return
        self.models_page.set_busy(True, "正在处理模型…")
        worker = ModelWorker(self.model_manager, action, model_id, source, self)
        worker.progressChanged.connect(self.models_page.set_progress)
        worker.succeeded.connect(self._on_model_job_ok)
        worker.failed.connect(self._on_model_job_fail)
        self._model_worker = worker
        worker.start()

    def _on_model_job_ok(self, action: str, path: object) -> None:
        self.models_page.set_busy(False, f"{action} 完成：{path}")
        self.refresh_models()
        self._set_status(f"模型{action}完成：{path}")

    def _on_model_job_fail(self, message: str) -> None:
        self.models_page.set_busy(False, message)
        QMessageBox.warning(self, "模型", message)
        self.refresh_models()

    def refresh_hardware(self) -> EnvironmentReport:
        self._report = HardwareManager().detect()
        self._perf = PerformanceRuntime(self._report)
        for engine in (self.speech_engine, self.ocr_engine, self.translation_engine):
            if hasattr(engine, "_report"):
                engine._report = self._perf.report
        self._apply_hardware_display()
        self._set_status(strings.STATUS_HARDWARE)
        return self._report

    def _apply_hardware_display(self) -> None:
        snap = self._perf.snapshot()
        self.hardware_status.setText(snap.status_text())
        self.side_panel.set_hardware_text(snap.detail_text())
        self.settings_page.set_hardware(snap.cpu, snap.gpu, snap.vram, snap.ram, snap.profile_label)

    def _begin_heavy_job(self, name: str) -> bool:
        if self._perf.jobs.try_acquire(name):
            return True
        QMessageBox.information(self, strings.APP_TITLE, self._perf.busy_message())
        self._set_status(self._perf.busy_message())
        return False

    def _end_heavy_job(self, name: str) -> None:
        self._perf.jobs.release(name)

    def open_log_directory(self) -> Path:
        path = logs_dir()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        return path

    def _build(self) -> None:
        self._build_menus()
        self._build_page_bar()
        self.project_list = ProjectListPanel()
        self.project_list.selection_changed.connect(self._on_list_selection)
        self.video_stage = VideoStage()
        self.subtitle_page = SubtitlePage()
        self.subtitle_page.importClicked.connect(self._dialog_add_subtitle)
        self.subtitle_page.saveClicked.connect(self.save_subtitle)
        self.subtitle_page.saveAsClicked.connect(self.save_subtitle_as)
        self.subtitle_page.filesDropped.connect(self._on_subtitle_files_dropped)
        self.subtitle_page.previewEmbeddedClicked.connect(self.preview_embedded_subtitle)
        self.subtitle_page.extractEmbeddedClicked.connect(self.extract_embedded_subtitle)
        self.subtitle_page.documentChanged.connect(self._on_subtitle_document_changed)
        self.subtitle_page.cueSelected.connect(self._on_table_cue_selected)
        self.subtitle_page.statusMessage.connect(self._set_status)
        self.subtitle_page.findClicked.connect(self.open_find_replace)
        self.subtitle_page.qualityCheckClicked.connect(self.run_quality_check)
        self.subtitle_page.qualityJumpClicked.connect(self.jump_quality_issue)
        self.subtitle_page.qualityConfirmClicked.connect(self.confirm_selected_quality)
        self.subtitle_page.qualityLockClicked.connect(self.lock_confirmed_cues)
        self.subtitle_page.qualityFilterChanged.connect(self._sync_quality_filter_controls)
        self.subtitle_page.issueActivated.connect(self._on_quality_issue_activated)
        self.workspace_page = QWidget()
        self.workspace_page.setObjectName("workspacePage")
        workspace_hint = QLabel("左侧是视频。下方是音频波形和字幕时间轴。打开「字幕编辑」可同时看到字幕列表。")
        workspace_hint.setWordWrap(True)
        workspace_hint.setObjectName("workspaceHint")
        workspace_layout = QVBoxLayout(self.workspace_page)
        workspace_layout.setContentsMargins(16, 12, 16, 12)
        workspace_layout.addWidget(workspace_hint)
        workspace_layout.addStretch(1)
        self.batch_page = BatchPage()
        self.models_page = ModelsPage()
        self.project_page = ProjectPage()
        self.settings_page = SettingsPage()
        self.side_panel = SidePanel()
        self.timeline = TimelinePanel()
        self.editor_tracks = EditorTracksPanel()
        self.playback.set_video_output(self.video_stage.video_widget)
        self.video_stage.filesDropped.connect(self._on_files_dropped)
        self._connect_playback()
        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        for widget in (
            self.workspace_page,
            self.subtitle_page,
            self.batch_page,
            self.models_page,
            self.project_page,
            self.settings_page,
        ):
            self.page_stack.addWidget(widget)
        self._page_index = {page_id: index for index, (page_id, _) in enumerate(PAGES)}
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.top_splitter.setObjectName("topSplitter")
        self.top_splitter.addWidget(self.video_stage)
        self.top_splitter.addWidget(self.page_stack)
        self.top_splitter.setStretchFactor(0, 1)
        self.top_splitter.setStretchFactor(1, 1)
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.center_splitter.setObjectName("centerSplitter")
        self.center_splitter.addWidget(self.top_splitter)
        self.center_splitter.addWidget(self.editor_tracks)
        self.center_splitter.addWidget(self.timeline)
        self.center_splitter.setStretchFactor(0, 1)
        self.center_splitter.setStretchFactor(1, 0)
        self.center_splitter.setStretchFactor(2, 0)
        self.center_splitter.setSizes([420, 170, 110])
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.addWidget(self.project_list)
        self.main_splitter.addWidget(self.center_splitter)
        self.main_splitter.addWidget(self.side_panel)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([240, 760, 300])
        self.setCentralWidget(self.main_splitter)
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_label = status
        self.status_label.setObjectName("statusLabel")
        self.hardware_status = QLabel()
        self.hardware_status.setObjectName("hardwareStatusLabel")
        status.addPermanentWidget(self.hardware_status)
        self.batch_page.add_button.clicked.connect(self._dialog_add_batch)
        self.batch_page.start_button.clicked.connect(self.start_batch)
        self.batch_page.pause_button.clicked.connect(self.pause_batch)
        self.batch_page.resume_button.clicked.connect(self.resume_batch)
        self.batch_page.cancel_button.clicked.connect(self.cancel_batch)
        self.batch_page.retry_button.clicked.connect(self.retry_batch)
        self.batch_page.remove_button.clicked.connect(self.delete_batch_selected)
        self.models_page.refresh_button.clicked.connect(self.refresh_models)
        self.models_page.install_button.clicked.connect(self.install_selected_model)
        self.models_page.delete_button.clicked.connect(self.delete_selected_model)
        self.models_page.switch_button.clicked.connect(self.switch_selected_model)
        self.models_page.import_button.clicked.connect(self.import_local_model)
        self.models_page.enable_button.clicked.connect(self.enable_selected_model)
        self.models_page.disable_button.clicked.connect(self.disable_selected_model)
        self.models_page.change_dir_button.clicked.connect(self.change_models_directory)
        self.settings_page.models_dir_browse.clicked.connect(self.change_models_directory)
        self.settings_page.projects_dir_browse.clicked.connect(self.change_projects_directory)
        self.settings_page.cache_dir_browse.clicked.connect(self.change_cache_directory)
        self.settings_page.save_button.clicked.connect(self.save_user_settings)
        self.settings_page.import_license_button.clicked.connect(self.import_license_file)
        self.settings_page.check_update_button.clicked.connect(self.check_for_update)
        self.settings_page.export_diag_button.clicked.connect(self.export_diagnostics)
        self.settings_page.theme_combo.currentIndexChanged.connect(self._on_theme_combo)
        self.side_panel.device_combo.currentIndexChanged.connect(self._on_device_combo)
        self.side_panel.language_combo.currentIndexChanged.connect(self._on_language_combo)
        self.side_panel.transcribe_button.clicked.connect(self.start_transcription)
        self.side_panel.ocr_button.clicked.connect(self.start_ocr)
        self.side_panel.pick_ocr_region_button.clicked.connect(self.pick_ocr_region)
        self.side_panel.translate_button.clicked.connect(self.start_translation)
        self.side_panel.resources_button.clicked.connect(self.edit_translation_resources)
        self.side_panel.diarize_button.clicked.connect(self.start_diarization)
        self.side_panel.speaker_map_button.clicked.connect(self.edit_speaker_map)
        self.side_panel.quality_button.clicked.connect(self.run_quality_check)
        self.side_panel.quality_jump_button.clicked.connect(self.jump_quality_issue)
        self.side_panel.quality_confirm_button.clicked.connect(self.confirm_selected_quality)
        self.side_panel.quality_lock_button.clicked.connect(self.lock_confirmed_cues)
        self.side_panel.hardsub_button.clicked.connect(self.start_hardsub)
        self.side_panel.quality_filter_box.toggled.connect(self.set_quality_filter_below_90)
        self.side_panel.realtime_button.clicked.connect(self.toggle_realtime)
        self.side_panel.realtime_delay_combo.currentIndexChanged.connect(self._update_realtime_actual_label)
        self.side_panel.realtime_profile_combo.currentIndexChanged.connect(self._update_realtime_actual_label)
        self._apply_editor_layout("workspace")

    def _connect_playback(self) -> None:
        self.timeline.playClicked.connect(self.playback.play)
        self.timeline.pauseClicked.connect(self.playback.pause)
        self.timeline.stopClicked.connect(self.playback.stop)
        self.timeline.skipBackwardClicked.connect(lambda: self.playback.skip_ms(-5000))
        self.timeline.skipForwardClicked.connect(lambda: self.playback.skip_ms(5000))
        self.timeline.seekRequested.connect(self.playback.seek_ms)
        self.timeline.volumeChanged.connect(lambda value: self.playback.set_volume(value / 100))
        self.timeline.muteToggled.connect(self.playback.set_muted)
        self.timeline.rateChanged.connect(self.playback.set_rate)
        self.timeline.fullscreenClicked.connect(self.video_stage.enter_fullscreen)
        self.playback.positionChanged.connect(self.timeline.set_position_ms)
        self.playback.positionChanged.connect(self._on_realtime_position)
        self.playback.durationChanged.connect(self.timeline.set_duration_ms)
        self.playback.positionChanged.connect(self.editor_tracks.waveform.set_position_ms)
        self.playback.positionChanged.connect(self.editor_tracks.cue_timeline.set_position_ms)
        self.playback.durationChanged.connect(self._on_duration_for_editor)
        self.playback.errorOccurred.connect(self._on_playback_error)
        self.playback.stateChanged.connect(self._on_playback_state)
        self.editor_tracks.waveform.seekRequested.connect(self.playback.seek_ms)
        self.editor_tracks.cue_timeline.seekRequested.connect(self.playback.seek_ms)
        self.editor_tracks.cue_timeline.cueSelected.connect(self._on_timeline_cue_selected)
        self.editor_tracks.cue_timeline.cueDragStarted.connect(self._on_cue_drag_started)
        self.editor_tracks.cue_timeline.cueTimesChanged.connect(self._on_cue_times_changed)
        self.editor_tracks.cue_timeline.cueDragFinished.connect(self._on_cue_drag_finished)

    def _on_files_dropped(self, paths: list[str]) -> None:
        for item in paths:
            self.add_video_path(Path(item))

    def _on_subtitle_files_dropped(self, paths: list[str]) -> None:
        for item in paths:
            self.add_subtitle_path(Path(item))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and collect_video_paths(list(event.mimeData().urls())):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = collect_video_paths(list(event.mimeData().urls()))
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        for path in paths:
            if self._current_page == "batch":
                self.add_batch_path(path)
            else:
                self.add_video_path(path)

    def _on_playback_error(self, message: str) -> None:
        self.timeline.set_media_ready(False, message)
        self._set_status(message)

    def _on_playback_state(self, state: str) -> None:
        if self.playback.source_path is None:
            return
        name = self.playback.source_path.name
        labels = {"playing": "播放中", "paused": "已暂停", "stopped": "已停止"}
        self._set_status(f"{labels.get(state, state)}：{name}")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and not self._focus_is_text():
            if self.playback.source_path is not None:
                self.playback.toggle_play()
                event.accept()
                return
        super().keyPressEvent(event)

    def _focus_is_text(self) -> bool:
        widget = QApplication.focusWidget()
        if widget is None:
            return False
        if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return True
        parent = widget.parentWidget()
        return isinstance(parent, (QLineEdit, QTextEdit, QPlainTextEdit))

    def _apply_editor_layout(self, page_id: str) -> None:
        if not hasattr(self, "top_splitter"):
            return
        if page_id == "workspace":
            self.top_splitter.setSizes([780, 220])
        elif page_id == "subtitles":
            self.top_splitter.setSizes([420, 580])
        else:
            self.top_splitter.setSizes([280, 720])

    def _on_duration_for_editor(self, duration_ms: int) -> None:
        self._sync_editor_duration(duration_ms)

    def _sync_editor_duration(self, duration_ms: int | None = None) -> None:
        duration = int(duration_ms if duration_ms is not None else self.playback.duration_ms())
        document = self.subtitle_page.document
        if document and document.segments:
            duration = max(duration, max(item.end_time for item in document.segments), 1000)
        duration = max(duration, 1000)
        self.editor_tracks.waveform.set_duration_ms(duration)
        self.editor_tracks.cue_timeline.set_duration_ms(duration)

    def _on_subtitle_document_changed(self) -> None:
        document = self.subtitle_page.document
        segments = document.segments if document is not None else []
        self.editor_tracks.cue_timeline.set_segments(segments)
        self._mark_project_dirty()
        self._sync_editor_duration()

    def _on_table_cue_selected(self, index: int) -> None:
        self.editor_tracks.cue_timeline.set_selected(index)

    def _on_timeline_cue_selected(self, index: int) -> None:
        self.subtitle_page.select_row(index)

    def _on_cue_drag_started(self) -> None:
        self.subtitle_page.editor.begin_gesture()

    def _on_cue_times_changed(self, index: int, start_ms: int, end_ms: int) -> None:
        editor = self.subtitle_page.editor
        if editor.document is None:
            return
        try:
            editor.resize(index, start_ms=start_ms, end_ms=end_ms)
        except SubtitleError as exc:
            self._set_status(str(exc))
            return
        self.editor_tracks.cue_timeline.update()

    def _on_cue_drag_finished(self) -> None:
        self.subtitle_page.editor.end_gesture()
        self.subtitle_page.refresh_table()
        self.subtitle_page.documentChanged.emit()

    def _stop_waveform_worker(self, timeout_ms: int = 10_000) -> None:
        worker = self._waveform_worker
        if worker is None:
            return
        if worker.isRunning():
            worker.requestInterruption()
            worker.wait(timeout_ms)
            if worker.isRunning():
                self._logger.warning("Waveform worker still running after %s ms", timeout_ms)
        self._waveform_worker = None

    def _load_waveform(self, path: Path) -> None:
        self._stop_waveform_worker()
        self.editor_tracks.waveform.set_peaks(None)
        worker = WaveformWorker(path, self)
        worker.succeeded.connect(self.editor_tracks.waveform.set_peaks)
        worker.failed.connect(self._set_status)
        self._waveform_worker = worker
        worker.start()

    def open_find_replace(self, _checked: bool = False) -> None:
        if self.subtitle_page.document is None:
            self._set_status("没有打开的字幕")
            return
        self.switch_page("subtitles")
        if self._find_dialog is None:
            dialog = FindReplaceDialog(self)
            dialog.find_button.clicked.connect(self._find_next)
            dialog.replace_button.clicked.connect(self._replace_all)
            self._find_dialog = dialog
        self._find_dialog.show()
        self._find_dialog.raise_()
        self._find_dialog.find_edit.setFocus()

    def _find_next(self) -> None:
        dialog = self._find_dialog
        if dialog is None or self.subtitle_page.document is None:
            return
        needle = dialog.needle()
        hits = self.subtitle_page.editor.find(needle, dialog.fields())
        if not hits:
            dialog.set_status("未找到")
            return
        current = self.subtitle_page.selected_indexes()
        start = current[0] if current else -1
        chosen = hits[0]
        for index, field in hits:
            if index > start:
                chosen = (index, field)
                break
        self.subtitle_page.select_row(chosen[0])
        dialog.set_status(f"第 {chosen[0] + 1} 条 · {chosen[1]}（共 {len(hits)} 处）")

    def _replace_all(self) -> None:
        dialog = self._find_dialog
        if dialog is None or self.subtitle_page.document is None:
            return
        try:
            changed = self.subtitle_page.editor.replace(dialog.needle(), dialog.replacement(), dialog.fields())
        except SubtitleError as exc:
            dialog.set_status(str(exc))
            return
        self.subtitle_page.refresh_table()
        self.subtitle_page.documentChanged.emit()
        dialog.set_status(f"已替换 {changed} 处（锁定条目已跳过）")

    def _build_page_bar(self) -> None:
        toolbar = QToolBar("页面")
        toolbar.setObjectName("pageToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        group = QActionGroup(self)
        group.setExclusive(True)
        self._page_actions: dict[str, QAction] = {}
        for page_id, title in PAGES:
            action = QAction(title, self)
            action.setCheckable(True)
            action.setData(page_id)
            action.setObjectName(f"pageAction_{page_id}")
            action.triggered.connect(lambda checked=False, pid=page_id: self.switch_page(pid))
            group.addAction(action)
            toolbar.addAction(action)
            self._page_actions[page_id] = action
        self._page_actions["workspace"].setChecked(True)

    def _build_menus(self) -> None:
        menubar = self.menuBar()
        menubar.setObjectName("mainMenuBar")
        file_menu = menubar.addMenu(strings.MENU_FILE)
        self._act("addVideo", strings.ADD_VIDEO, file_menu, self._dialog_add_video)
        self._act("addSubtitle", strings.ADD_SUBTITLE, file_menu, self._dialog_add_subtitle)
        self._act("saveSubtitle", "保存字幕", file_menu, self.save_subtitle, QKeySequence.StandardKey.Save)
        self._act("saveSubtitleAs", "字幕另存为...", file_menu, self.save_subtitle_as)
        self._act("extractEmbedded", "提取内嵌字幕", file_menu, self.extract_embedded_subtitle)
        export_action = self._act("exportMedia", strings.EXPORT, file_menu, self.export_media)
        unlock_action(export_action, "导出字幕文件、内嵌轨道、烧录成片或完整项目。只改字幕时优先 remux。")
        file_menu.addSeparator()
        self._act("exit", strings.EXIT, file_menu, self.close)

        edit_menu = menubar.addMenu("编辑")
        self._act("undo", "撤销", edit_menu, lambda: self.subtitle_page.undo(), QKeySequence.StandardKey.Undo)
        self._act("redo", "重做", edit_menu, lambda: self.subtitle_page.redo(), QKeySequence("Ctrl+Shift+Z"))
        edit_menu.addSeparator()
        self._act("findReplace", "查找/替换", edit_menu, self.open_find_replace, QKeySequence.StandardKey.Find)
        edit_menu.addSeparator()
        self._act("addCue", "新增字幕", edit_menu, lambda: self.subtitle_page.add_cue(self.playback.position_ms()))
        self._act("deleteCue", "删除字幕", edit_menu, lambda: self.subtitle_page.delete_selected())
        self._act("splitCue", "拆分字幕", edit_menu, lambda: self.subtitle_page.split_selected(self.playback.position_ms()))
        self._act("mergeCue", "合并字幕", edit_menu, lambda: self.subtitle_page.merge_selected())

        project_menu = menubar.addMenu(strings.MENU_PROJECT)
        self._act("newProject", strings.NEW_PROJECT, project_menu, self._dialog_new_project)
        self._act("openProject", strings.OPEN_PROJECT, project_menu, self._dialog_open_project)
        self._act("saveProject", strings.SAVE_PROJECT, project_menu, self._menu_save_project)
        self._act("saveProjectAs", strings.SAVE_PROJECT_AS, project_menu, self._dialog_save_project_as)
        project_menu.addSeparator()
        self._act("removeSelected", strings.REMOVE_SELECTED, project_menu, self.remove_selected_media)

        tools_menu = menubar.addMenu(strings.MENU_TOOLS)
        self._act("detectHardware", strings.DETECT_HARDWARE, tools_menu, self.refresh_hardware)
        self._act("openLogs", strings.OPEN_LOG_DIR, tools_menu, self.open_log_directory)

        ai_menu = menubar.addMenu(strings.MENU_AI)
        self._act("openModels", strings.OPEN_MODELS_PAGE, ai_menu, lambda: self.switch_page("models"))
        transcribe = self._act("menuTranscribe", strings.START_TRANSCRIBE, ai_menu, self.start_transcription)
        ocr = self._act("menuOcr", strings.START_OCR, ai_menu, self.start_ocr)
        translate = self._act("menuTranslate", strings.START_TRANSLATE, ai_menu, self.start_translation)
        realtime = self._act("menuRealtime", strings.START_REALTIME, ai_menu, self.toggle_realtime)
        resources = self._act("menuTranslationResources", strings.EDIT_TRANSLATION_RESOURCES, ai_menu, self.edit_translation_resources)
        diarize = self._act("menuDiarize", strings.START_DIARIZE, ai_menu, self.start_diarization)
        speaker_map = self._act("menuSpeakerMap", strings.EDIT_SPEAKER_MAP, ai_menu, self.edit_speaker_map)
        quality = self._act("menuQualityCheck", strings.START_QUALITY_CHECK, ai_menu, self.run_quality_check)
        quality_filter = self._act("menuQualityFilter", strings.FILTER_BELOW_90, ai_menu, None)
        quality_filter.setCheckable(True)
        quality_filter.toggled.connect(self.set_quality_filter_below_90)
        quality_jump = self._act("menuQualityJump", strings.JUMP_QUALITY_ISSUE, ai_menu, self.jump_quality_issue)
        quality_confirm = self._act("menuQualityConfirm", strings.CONFIRM_QUALITY, ai_menu, self.confirm_selected_quality)
        quality_lock = self._act("menuQualityLock", strings.LOCK_CONFIRMED, ai_menu, self.lock_confirmed_cues)
        hardsub = self._act("menuHardSub", strings.START_HARDSUB, ai_menu, self.start_hardsub)
        unlock_action(transcribe, "使用本机模型识别当前视频音轨")
        unlock_action(ocr, "使用本机 RapidOCR 识别硬字幕")
        unlock_action(translate, "使用本机目录模型翻译当前字幕")
        unlock_action(realtime, "播放时后台识别并翻译，字幕叠在画面上")
        unlock_action(resources, "编辑术语表、翻译记忆和人名字典")
        unlock_action(diarize, "本机说话人分离，模型缺失时保持普通字幕")
        unlock_action(speaker_map, "修改 Speaker 1 显示名并设置人物样式")
        unlock_action(quality, "识别后纠错、翻译审核和 QA。绿色高质量，黄色建议检查，红色需要人工检查")
        unlock_action(quality_filter, "只显示综合评分低于 90 的字幕")
        unlock_action(quality_jump, "一键跳到下一条问题字幕并定位时间")
        unlock_action(quality_confirm, "人工确认当前字幕")
        unlock_action(quality_lock, "锁定已确认字幕，之后 AI 不能覆盖")
        unlock_action(hardsub, "定位并处理硬字幕：保留、覆盖或智能去除，生成真实视频")

        settings_menu = menubar.addMenu(strings.MENU_SETTINGS)
        self._act("openSettings", strings.OPEN_SETTINGS_PAGE, settings_menu, lambda: self.switch_page("settings"))
        self._act("saveSettings", strings.SAVE_SETTINGS, settings_menu, self.save_user_settings)

        help_menu = menubar.addMenu(strings.MENU_HELP)
        self._act("checkUpdate", strings.CHECK_UPDATE, help_menu, self.check_for_update)
        self._act("about", strings.ABOUT, help_menu, self._show_about)
        self._act("environment", strings.ENVIRONMENT, help_menu, self._show_environment)

    def _act(self, object_name: str, text: str, menu, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.setObjectName(f"action_{object_name}")
        if shortcut is not None:
            action.setShortcut(shortcut)
        if slot is not None:
            action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _append_media(self, key: str, path: Path, extra: dict | None = None) -> None:
        resolved = path.expanduser().resolve()
        record = {"path": str(resolved), "name": resolved.name}
        if extra:
            record.update(extra)
        items = list(self._project.get(key, []))
        if any(item.get("path") == record["path"] for item in items):
            self._refresh_project_views()
            return
        items.append(record)
        self._project[key] = items
        self._mark_project_dirty()
        self._refresh_project_views()

    def _refresh_project_views(self) -> None:
        videos = list(self._project.get("videos", []))
        subtitles = list(self._project.get("subtitles", []))
        self.project_list.set_items(videos, subtitles)
        self.subtitle_page.set_library_count(len(subtitles))
        self._sync_project_from_tasks()
        self.project_page.set_project(
            str(self._project.get("name") or strings.NO_PROJECT),
            self._project_path,
            len(videos),
            len(subtitles),
        )
        lines = [f"{item.get('name')}: {item.get('path')}" for item in subtitles]
        self.side_panel.set_subtitle_summary(lines)

    def _on_list_selection(self, kind: str, path: str) -> None:
        if kind == "video" and path:
            self._play_video(Path(path))
        elif kind == "subtitle" and path:
            self._open_subtitle(Path(path))

    def _load_settings_into_controls(self) -> None:
        self.settings_page.theme_combo.blockSignals(True)
        self.side_panel.device_combo.blockSignals(True)
        self.side_panel.language_combo.blockSignals(True)
        try:
            theme = str(self._settings.get("app.theme", "system"))
            index = self.settings_page.theme_combo.findData(theme)
            self.settings_page.theme_combo.setCurrentIndex(index if index >= 0 else 0)
            self.settings_page.prefer_gpu.setChecked(bool(self._settings.get("hardware.prefer_gpu", True)))
            device = str(self._settings.get("hardware.device", "auto"))
            d_index = self.side_panel.device_combo.findData(device)
            self.side_panel.device_combo.setCurrentIndex(d_index if d_index >= 0 else 0)
            language = str(self._settings.get("app.target_language", "zh-CN"))
            l_index = self.side_panel.language_combo.findData(language)
            self.side_panel.language_combo.setCurrentIndex(l_index if l_index >= 0 else 0)
            delay = normalize_delay_ms(int(self._settings.get("realtime.delay_ms", 3000) or 3000))
            d_pos = self.side_panel.realtime_delay_combo.findData(delay)
            self.side_panel.realtime_delay_combo.setCurrentIndex(d_pos if d_pos >= 0 else 1)
            profile = normalize_profile(str(self._settings.get("realtime.profile", "balanced")))
            p_pos = self.side_panel.realtime_profile_combo.findData(profile)
            self.side_panel.realtime_profile_combo.setCurrentIndex(p_pos if p_pos >= 0 else 2)
            device = str(self._settings.get("batch.device", self._settings.get("hardware.device", "auto")))
            b_index = self.batch_page.device_combo.findData(device)
            self.batch_page.device_combo.setCurrentIndex(b_index if b_index >= 0 else 0)
            self.batch_page.concurrent_spin.setValue(int(self._settings.get("batch.max_concurrent", 1) or 1))
            self.batch_page.cpu_spin.setValue(int(self._settings.get("batch.cpu_threads", 0) or 0))
            self.batch_page.ram_spin.setValue(float(self._settings.get("batch.ram_limit_gb", 0) or 0))
            export_fmt = str(self._settings.get("export.format", "srt") or "srt")
            e_index = self.settings_page.export_format.findData(export_fmt)
            self.settings_page.export_format.setCurrentIndex(e_index if e_index >= 0 else 0)
            self.settings_page.export_burn_in.setChecked(bool(self._settings.get("export.burn_in", False)))
            self._set_combo(self.settings_page.export_container, self._settings.get("export.container", "mp4"))
            self._set_combo(self.settings_page.export_codec, self._settings.get("export.video_codec", "copy"))
            self.settings_page.models_dir_edit.setText(str(self.model_manager.models_root()))
            self.settings_page.projects_dir_edit.setText(str(self._settings.get("paths.projects_dir") or projects_dir()))
            self.settings_page.cache_dir_edit.setText(str(self._settings.get("paths.cache_dir") or cache_dir()))
            self.settings_page.allow_network.setChecked(bool(self._settings.get("privacy.allow_network", False)))
            self.settings_page.update_source_edit.setText(str(self._settings.get("update.source") or ""))
            self._refresh_license_status()
        finally:
            self.settings_page.theme_combo.blockSignals(False)
            self.side_panel.device_combo.blockSignals(False)
            self.side_panel.language_combo.blockSignals(False)

    def _capture_settings_from_controls(self) -> None:
        self._settings.set("app.theme", self.settings_page.theme_combo.currentData())
        self._settings.set("hardware.prefer_gpu", self.settings_page.prefer_gpu.isChecked())
        self._settings.set("hardware.device", self.side_panel.device_combo.currentData())
        self._settings.set("app.target_language", self.side_panel.language_combo.currentData())
        self._settings.set("app.language", "zh-CN")
        self._settings.set("privacy.upload_media", False)
        self._settings.set("privacy.allow_network", bool(self.settings_page.allow_network.isChecked()))
        self._settings.set("update.source", str(self.settings_page.update_source_edit.text() or "").strip())
        self._settings.set("paths.models_dir", str(self.model_manager.models_root()))
        self._settings.set("paths.projects_dir", str(self.settings_page.projects_dir_edit.text() or projects_dir()))
        self._settings.set("paths.cache_dir", str(self.settings_page.cache_dir_edit.text() or cache_dir()))
        self._settings.set("realtime.delay_ms", int(self.side_panel.realtime_delay_combo.currentData() or 3000))
        self._settings.set("realtime.profile", str(self.side_panel.realtime_profile_combo.currentData() or "balanced"))
        self._apply_batch_limits()

    def _persist_layout(self) -> None:
        self._settings.set("ui.last_page", self._current_page)
        self._settings.set("ui.geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        self._settings.set("ui.main_splitter", self.main_splitter.sizes())
        self._settings.set("ui.center_splitter", self.center_splitter.sizes())

    def _restore_layout(self) -> None:
        geometry = self._settings.get("ui.geometry")
        if isinstance(geometry, str) and geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
        main_sizes = self._settings.get("ui.main_splitter")
        if isinstance(main_sizes, list) and len(main_sizes) == 3:
            self.main_splitter.setSizes([int(v) for v in main_sizes])
        center_sizes = self._settings.get("ui.center_splitter")
        if isinstance(center_sizes, list) and len(center_sizes) == 2:
            self.center_splitter.setSizes([int(v) for v in center_sizes])
        last_page = str(self._settings.get("ui.last_page", "workspace"))
        if last_page in self._page_index:
            self.switch_page(last_page)

    def _on_theme_combo(self) -> None:
        preference = str(self.settings_page.theme_combo.currentData() or "system")
        self.apply_theme_preference(preference)

    def _on_device_combo(self) -> None:
        self._settings.set("hardware.device", self.side_panel.device_combo.currentData())

    def _on_language_combo(self) -> None:
        self._settings.set("app.target_language", self.side_panel.language_combo.currentData())

    def _dialog_add_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, strings.ADD_VIDEO, "", VIDEO_FILTER)
        if path:
            self.add_video_path(Path(path))

    def _dialog_add_subtitle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, strings.ADD_SUBTITLE, "", SUBTITLE_FILTER)
        if path:
            self.add_subtitle_path(Path(path))

    def _dialog_add_batch(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "添加到批量队列", "", VIDEO_FILTER)
        for path in paths:
            self.add_batch_path(Path(path))

    def _apply_batch_limits(self) -> None:
        device = str(self.batch_page.device_combo.currentData() or "auto")
        prefer_gpu = device == "gpu" or (device == "auto" and self.settings_page.prefer_gpu.isChecked())
        self.batch_runner.set_limits(
            device=device,
            prefer_gpu=prefer_gpu,
            max_concurrent=int(self.batch_page.concurrent_spin.value()),
            ram_limit_gb=float(self.batch_page.ram_spin.value()),
            cpu_threads=int(self.batch_page.cpu_spin.value()),
            target_lang=str(self._settings.get("app.target_language", "zh-CN") or "zh-CN"),
        )
        self._settings.set("batch.device", device)
        self._settings.set("batch.prefer_gpu", prefer_gpu)
        self._settings.set("batch.max_concurrent", int(self.batch_page.concurrent_spin.value()))
        self._settings.set("batch.ram_limit_gb", float(self.batch_page.ram_spin.value()))
        self._settings.set("batch.cpu_threads", int(self.batch_page.cpu_spin.value()))
        self._settings.set("export.format", str(self.settings_page.export_format.currentData() or "srt"))
        self._settings.set("export.burn_in", bool(self.settings_page.export_burn_in.isChecked()))
        self._settings.set("export.container", str(self.settings_page.export_container.currentData() or "mp4"))
        self._settings.set("export.video_codec", str(self.settings_page.export_codec.currentData() or "copy"))

    def _sync_project_from_tasks(self) -> None:
        items = []
        for task in self.task_manager.list_tasks():
            payload = task.get("payload") or {}
            items.append(
                {
                    "task_id": task.get("id"),
                    "path": payload.get("path", ""),
                    "name": payload.get("name") or Path(str(payload.get("path") or "")).name,
                    "status": task.get("status") or "等待",
                    "stage": payload.get("current_stage") or "",
                    "export_path": payload.get("export_path") or "",
                    "export_video_path": payload.get("export_video_path") or "",
                    "warning": "; ".join(payload.get("warnings") or []),
                }
            )
        self._project["batch_items"] = items
        self.batch_page.set_items(items)
        self.batch_page.set_stats(self.batch_runner.stats())

    def _ensure_batch_worker(self) -> None:
        if self._batch_worker is not None and self._batch_worker.isRunning():
            return
        self._batch_worker = BatchWorker(self.batch_runner, self)
        self._batch_worker.changed.connect(self._on_batch_changed)
        self._batch_worker.failed.connect(self._on_batch_fail)
        self._batch_worker.finishedIdle.connect(self._on_batch_idle)
        self._batch_worker.start()

    def _on_batch_changed(self) -> None:
        self._sync_project_from_tasks()

    def _on_batch_fail(self, message: str) -> None:
        self._sync_project_from_tasks()
        self._set_status(message)
        self._logger.warning("%s", message)

    def _on_batch_idle(self) -> None:
        self._sync_project_from_tasks()
        stats = self.batch_runner.stats()
        if self.batch_runner.is_paused():
            self._set_status("批量处理已暂停，可继续")
            return
        self._set_status(
            f"批量队列空闲：完成 {stats.get('done', 0)}/{stats.get('total', 0)}，失败 {stats.get('failed', 0)}"
        )

    def _dialog_new_project(self) -> None:
        name, ok = QInputDialog.getText(self, strings.NEW_PROJECT, "项目名称")
        if not ok or not name.strip():
            return
        directory = QFileDialog.getExistingDirectory(self, "选择项目文件夹")
        if directory:
            self.new_project(name.strip(), Path(directory))

    def _dialog_open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, strings.OPEN_PROJECT, "", PROJECT_FILTER)
        if path:
            self.open_project(Path(path))

    def _menu_save_project(self) -> None:
        if self._project_path is None:
            self._dialog_save_project_as()
            return
        self.save_project()

    def _dialog_save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, strings.SAVE_PROJECT_AS, "project.vtproj", PROJECT_FILTER)
        if path:
            self.save_project_as(Path(path))

    def _refresh_license_status(self) -> None:
        info = load_license()
        if hasattr(self, "settings_page"):
            self.settings_page.license_status.setText(info.label)

    def import_license_file(self) -> None:
        import json

        picked, _ = QFileDialog.getOpenFileName(self, strings.IMPORT_LICENSE, "", "JSON (*.json)")
        if not picked:
            return
        source = Path(picked)
        info = load_license(source)
        if not info.valid:
            QMessageBox.warning(self, strings.IMPORT_LICENSE, f"授权无效，未导入。\n{info.reason}")
            self._refresh_license_status()
            return
        save_license(json.loads(source.read_text(encoding="utf-8")))
        self._refresh_license_status()
        self._set_status(f"已导入授权：{info.label}")

    def check_for_update(self) -> None:
        from localvideoai.core.exceptions import ConfigurationError
        from localvideoai.release.updater import check_for_update

        source = str(self.settings_page.update_source_edit.text() or self._settings.get("update.source") or "").strip()
        allow = bool(self.settings_page.allow_network.isChecked())
        try:
            info = check_for_update(source, allow_network=allow)
        except ConfigurationError as exc:
            QMessageBox.information(self, strings.CHECK_UPDATE, str(exc))
            return
        extra = f"\n{info.notes}" if info.notes else ""
        QMessageBox.information(self, strings.CHECK_UPDATE, f"{info.reason}{extra}\n来源：{info.source or '本机清单'}")
        self._set_status(info.reason)

    def export_diagnostics(self) -> None:
        path = export_crash_bundle()
        QMessageBox.information(
            self,
            strings.EXPORT_DIAGNOSTICS,
            f"已生成本机诊断包，未上传。\n{path}",
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        self._set_status(f"诊断包：{path}")

    def _show_about(self) -> None:
        info = load_license()
        QMessageBox.about(
            self,
            strings.ABOUT,
            f"{strings.APP_TITLE}\n版本 {__version__}\n{APP_DISPLAY_NAME}\n\n"
            f"{strings.PRIVACY_LOCAL}\n授权：{info.label}\n界面语言：简体中文\n",
        )

    def _show_environment(self) -> None:
        snap = self._perf.snapshot()
        QMessageBox.information(
            self,
            strings.ENVIRONMENT,
            f"{self._report.os_caption}\n"
            f"{snap.detail_text()}\n"
            f"自动GPU：{'是' if snap.auto_gpu else '否'}\n"
            f"Python：{self._report.python_version}\n"
            f"项目根：{self._report.project_root}",
        )

    def _update_status(self) -> None:
        title = dict(PAGES).get(self._current_page, self._current_page)
        project = self._project.get("name") or strings.NO_PROJECT
        dpi = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
        self.status_label.showMessage(
            f"{strings.STATUS_PAGE.format(page=title)}  |  项目：{project}  |  {strings.PRIVACY_LOCAL}  |  DPI {dpi:g}"
        )

    def _set_status(self, message: str) -> None:
        self.status_label.showMessage(message)
        self._logger.info("%s", message)

    def capture_project_state(self) -> dict[str, Any]:
        document = self.subtitle_page.document
        resources = getattr(self.translation_engine, "_resources", None)
        terms = {
            "glossary": entries_to_json(resources.load_user("glossary")) if resources else [],
            "translation_memory": entries_to_json(resources.load_user("translation_memory")) if resources else [],
            "character_dictionary": entries_to_json(resources.load_user("character_dictionary")) if resources else [],
        }
        source, targets, quality, device, prefer_gpu = self._translation_options()
        extra = [item for item in targets[1:]]
        models = dict(self.model_manager.active())
        speech_model = models.get("speech") or self._last_speech.get("model_id") or ""
        ocr_model = models.get("ocr") or self._last_ocr.get("model_id") or ""
        payload = merge_project(self._project)
        payload.update(
            {
                "name": self._project.get("name") or "未命名项目",
                "videos": list(self._project.get("videos") or []),
                "subtitles": list(self._project.get("subtitles") or []),
                "batch_items": list(self._project.get("batch_items") or []),
                "current_video": str(self.playback.source_path or self._project.get("current_video") or ""),
                "video_info": analysis_to_dict(self._last_analysis) or dict(self._project.get("video_info") or {}),
                "document": document_to_dict(document),
                "ocr": {
                    "region": list(self._ocr_region.as_tuple()) if self._ocr_region else self._last_ocr.get("region"),
                    "region_source": "manual" if self._ocr_region else str(self._last_ocr.get("region_source") or "auto"),
                    "language": self._last_ocr.get("language", ""),
                    "model_id": ocr_model,
                    "device": self._last_ocr.get("device", ""),
                },
                "speech": {
                    "language": self._last_speech.get("language") or str(self.side_panel.source_language_combo.currentData() or "auto"),
                    "model_id": speech_model,
                    "device": self._last_speech.get("device") or device,
                },
                "translation": {
                    "source_lang": source,
                    "target_lang": targets[0] if targets else "zh-CN",
                    "quality": quality,
                    "extra_targets": extra,
                },
                "speakers": {
                    "map": dict(document.speaker_map) if document else {},
                    "styles": dict(document.speaker_styles) if document else {},
                },
                "terms": terms,
                "timeline": {
                    "position_ms": self.playback.position_ms(),
                    "duration_ms": self.playback.duration_ms(),
                    "rate": self.playback.rate(),
                    "volume": self.playback.volume(),
                    "muted": self.playback.is_muted(),
                },
                "styles": {
                    "speaker_styles": dict(document.speaker_styles) if document else {},
                    "default_style": "",
                },
                "export": {
                    "format": str(self.settings_page.export_format.currentData() or "srt"),
                    "burn_in": bool(self.settings_page.export_burn_in.isChecked()),
                    "output_dir": str(self._settings.get("export.output_dir", "") or ""),
                    "container": str(self.settings_page.export_container.currentData() or "mp4"),
                    "video_codec": str(self.settings_page.export_codec.currentData() or "copy"),
                },
                "models": {
                    "speech": speech_model,
                    "ocr": ocr_model,
                    "translation": models.get("translation", ""),
                    "speaker": models.get("speaker", ""),
                    "device": device,
                    "prefer_gpu": prefer_gpu,
                },
                "tasks": self.task_manager.list_tasks(),
                "locks": lock_ids(document),
                "session": {"last_page": self._current_page},
                "dirty": self._project_dirty,
            }
        )
        return payload

    def apply_project_state(self, data: dict[str, Any], *, project_path: Path | None = None, play_video: bool = True) -> None:
        payload = merge_project(data)
        self._project = payload
        if project_path is not None:
            self._project_path = project_path
        document = document_from_dict(payload.get("document"))
        speakers = payload.get("speakers") or {}
        if document is not None:
            document.speaker_map = dict(speakers.get("map") or document.speaker_map)
            document.speaker_styles = dict(speakers.get("styles") or payload.get("styles", {}).get("speaker_styles") or document.speaker_styles)
            self.subtitle_page.set_document(document)
        else:
            self.subtitle_page.clear()
        terms = payload.get("terms") or {}
        resources = ProjectTranslationResources(terms)
        self.translation_engine._resources = resources
        translation = payload.get("translation") or {}
        self._set_combo(self.side_panel.language_combo, translation.get("target_lang", "zh-CN"))
        self._set_combo(self.side_panel.source_language_combo, translation.get("source_lang", "auto"))
        self._set_combo(self.side_panel.quality_combo, translation.get("quality", "standard"))
        extras = set(translation.get("extra_targets") or [])
        self.side_panel.extra_zh.setChecked("zh" in extras or "zh-CN" in extras)
        self.side_panel.extra_en.setChecked("en" in extras)
        self.side_panel.extra_ja.setChecked("ja" in extras)
        models = payload.get("models") or {}
        self._set_combo(self.side_panel.device_combo, models.get("device", "auto"))
        for capability in ("speech", "ocr", "translation", "speaker"):
            model_id = str(models.get(capability) or "")
            if model_id:
                self.model_manager._active[capability] = model_id
        export = payload.get("export") or {}
        self._set_combo(self.settings_page.export_format, export.get("format", "srt"))
        self.settings_page.export_burn_in.setChecked(bool(export.get("burn_in")))
        self._set_combo(self.settings_page.export_container, export.get("container", "mp4"))
        self._set_combo(self.settings_page.export_codec, export.get("video_codec", "copy"))
        self._settings.set("export.format", export.get("format", "srt"))
        self._settings.set("export.burn_in", bool(export.get("burn_in")))
        self._settings.set("export.output_dir", str(export.get("output_dir") or ""))
        self._settings.set("export.container", export.get("container", "mp4"))
        self._settings.set("export.video_codec", export.get("video_codec", "copy"))
        ocr = payload.get("ocr") or {}
        region = ocr.get("region")
        if isinstance(region, (list, tuple)) and len(region) == 4:
            self._ocr_region = NormalizedRegion(float(region[0]), float(region[1]), float(region[2]), float(region[3]))
            self.side_panel.ocr_region_combo.setCurrentIndex(1)
        else:
            self._ocr_region = None
        self._last_speech = dict(payload.get("speech") or {})
        self._last_ocr = dict(ocr)
        info = payload.get("video_info") or {}
        self._last_analysis = analysis_from_dict(info)
        if self._last_analysis is not None:
            self.side_panel.media_info.set_analysis(self._last_analysis)
        self._restore_project_tasks(str(payload.get("project_id") or ""), list(payload.get("tasks") or []))
        self._refresh_project_views()
        timeline = payload.get("timeline") or {}
        current = Path(str(payload.get("current_video") or ""))
        videos = list(payload.get("videos") or [])
        if play_video and current.is_file() and current.stat().st_size > 0:
            self._play_video(current, autoplay=False, position_ms=int(timeline.get("position_ms") or 0))
        elif play_video and videos:
            first = Path(str(videos[0].get("path") or ""))
            if first.is_file() and first.stat().st_size > 0:
                self._play_video(first, autoplay=False, position_ms=int(timeline.get("position_ms") or 0))
            elif first:
                self.video_stage.show_media(str(first))
        if timeline:
            try:
                self.playback.set_rate(float(timeline.get("rate") or 1.0))
                self.playback.set_volume(float(timeline.get("volume") or 0.8))
                self.playback.set_muted(bool(timeline.get("muted")))
            except MediaError:
                pass
        page = str((payload.get("session") or {}).get("last_page") or "")
        if page in self._page_index:
            self.switch_page(page)
        self._project["locks"] = lock_ids(document)
        self._project_dirty = False

    def prompt_unfinished_if_needed(self) -> str | None:
        if os.environ.get("LOCALVIDEOAI_SKIP_RECOVERY") == "1":
            return None
        if not bool(self._settings.get("project.prompt_recovery", True)):
            return None
        pending = self._recovery.unfinished()
        if pending is None:
            return None
        detail = pending.get("project_path") or pending.get("autosave_path") or ""
        choice = ask_unfinished(self, str(detail))
        if choice == ABANDON:
            self._recovery.clear()
            self._set_status("已放弃未完成的项目")
            return ABANDON
        snapshot = pending.get("autosave")
        if snapshot is None and pending.get("project_path"):
            snapshot = self._projects.load(Path(str(pending["project_path"])))
        if snapshot is None:
            self._set_status("没有可恢复的自动保存")
            return choice
        if choice == SAVE:
            target = pending.get("project_path")
            if not target:
                path, _ = QFileDialog.getSaveFileName(self, strings.SAVE_PROJECT_AS, "project.vtproj", PROJECT_FILTER)
                if not path:
                    return SAVE
                target = path
            saved = self._projects.save(Path(str(target)), merge_project(snapshot))
            self.apply_project_state(self._projects.load(saved), project_path=saved)
            self._recovery.clear()
            self._set_status(strings.STATUS_PROJECT_SAVED.format(path=saved))
            return SAVE
        project_path = Path(str(pending["project_path"])) if pending.get("project_path") else None
        self.apply_project_state(snapshot, project_path=project_path)
        self._mark_project_dirty()
        self._set_status("已恢复未完成的项目")
        return RECOVER

    def recover_unfinished(self) -> dict[str, Any] | None:
        pending = self._recovery.unfinished()
        if pending is None or pending.get("autosave") is None:
            return None
        path = Path(str(pending["project_path"])) if pending.get("project_path") else None
        self.apply_project_state(pending["autosave"], project_path=path)
        self._mark_project_dirty()
        return pending["autosave"]

    def abandon_unfinished(self) -> None:
        self._recovery.clear()

    def _start_autosave_timer(self) -> None:
        seconds = int(self._settings.get("project.autosave_seconds", 15) or 15)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setObjectName("projectAutosaveTimer")
        self._autosave_timer.setInterval(max(3, seconds) * 1000)
        self._autosave_timer.timeout.connect(self.autosave_project)
        self._autosave_timer.start()

    def autosave_project(self) -> Path | None:
        if not self._project_dirty:
            return None
        snapshot = self.capture_project_state()
        return self._recovery.write_autosave(snapshot)

    def _mark_project_dirty(self) -> None:
        self._project_dirty = True
        self._recovery.mark_dirty(self._project_path)

    def _store_video_info(self, path: Path, analysis) -> None:
        record = analysis_to_dict(analysis)
        items = list(self._project.get("videos") or [])
        found = False
        for item in items:
            if item.get("path") == str(path.expanduser().resolve()):
                item["info"] = record
                found = True
                break
        if found:
            self._project["videos"] = items
        self._project["video_info"] = record
        self._project["current_video"] = str(path.expanduser().resolve())

    def _restore_project_tasks(self, project_id: str, tasks: list[dict[str, Any]]) -> None:
        if project_id:
            for item in self.task_manager.list_tasks():
                payload = item.get("payload") or {}
                if payload.get("project_id") == project_id:
                    self.task_manager.delete(str(item["id"]))
        for item in tasks:
            payload = dict(item.get("payload") or {})
            if project_id:
                payload["project_id"] = project_id
            task_id = str(item.get("id") or "")
            if task_id and self.task_manager.get(task_id) is None:
                self.task_manager.enqueue(
                    TaskSpec(task_id=task_id, task_type=str(item.get("type") or "batch_video"), payload=payload)
                )
            elif not task_id:
                task_id = self.task_manager.enqueue(
                    TaskSpec(task_id="", task_type=str(item.get("type") or "batch_video"), payload=payload)
                )
            self.task_manager.update(task_id, status=str(item.get("status") or "等待"), payload=payload)

    def _set_combo(self, combo, value: object) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findData(str(value or ""))
        if index >= 0:
            combo.setCurrentIndex(index)

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self.stop_realtime() if self._realtime_active else None
            self._stop_realtime_worker()
            self._stop_waveform_worker()
            self.batch_runner.pause()
            self._apply_batch_limits()
            self._sync_project_from_tasks()
            if os.environ.get("LOCALVIDEOAI_SKIP_RECOVERY") != "1":
                snapshot = self.capture_project_state()
                if self._project_dirty:
                    self._recovery.write_autosave(snapshot)
                    self._recovery.mark_dirty(self._project_path)
                elif self._project_path is not None:
                    self._projects.save(self._project_path, snapshot)
                    self._recovery.mark_closed()
                else:
                    self._recovery.mark_closed()
            self.video_stage.exit_fullscreen()
            self.playback.close()
            self._capture_settings_from_controls()
            self._persist_layout()
            self._settings.save()
        except Exception:
            self._logger.exception("Failed to persist UI settings on close.")
            raise
        super().closeEvent(event)
