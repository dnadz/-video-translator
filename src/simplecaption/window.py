"""Drop a video, recognize its speech, then translate the lines."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidgetItem,
    QWidget,
    QMessageBox,
)

from localvideoai.engines.ctranslate2_translation_engine import CTranslate2TranslationEngine
from localvideoai.engines.faster_whisper_engine import FasterWhisperSpeechEngine
from localvideoai.speech.persist import transcript_to_document
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.timecodes import format_srt_timestamp
from localvideoai.translation.context import context_hint_for
from localvideoai.ui.workers.transcribe_worker import TranscribeWorker
from localvideoai.ui.workers.translate_worker import TranslateWorker
from simplecaption.cover_worker import CoverWorker
from simplecaption.runtime import prepare_runtime
from simplecaption.srtio import save_role_srt

_VIDEO_SUFFIXES = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".m4v",
    ".wmv",
    ".flv",
    ".ts",
    ".m2ts",
    ".mpeg",
    ".rmvb",
    ".rm",
    ".mpg",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
}

_SOURCE_LANGS = (
    ("自动检测", "auto"),
    ("中文", "zh"),
    ("English", "en"),
    ("日本語", "ja"),
)
_TARGET_LANGS = (
    ("中文", "zh"),
    ("English", "en"),
    ("日本語", "ja"),
)
_QUALITIES = (
    ("极速", "fast"),
    ("标准", "standard"),
    ("高质量", "high"),
)


class DropCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(88)
        self._handler = None

    def set_handler(self, handler) -> None:
        self._handler = handler

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._handler is not None:
            self._handler()
        super().mousePressEvent(event)


class SimpleWindow(QWidget):
    def __init__(self, settings=None, report=None) -> None:
        super().__init__()
        prepare_runtime()
        self.setWindowTitle("LocalVideoAI")
        self.setAcceptDrops(True)
        self.resize(1100, 820)
        self.setMinimumSize(800, 640)
        self._settings = settings
        self._report = report
        self._full_window = None
        self._media: Path | None = None
        self._document: SubtitleDocument | None = None
        self._busy = False
        self._speech = None
        self._translation = None
        self._transcribe_worker: TranscribeWorker | None = None
        self._translate_worker: TranslateWorker | None = None
        self._cover_worker: CoverWorker | None = None
        self._translate_next = False
        self._pipeline = False
        self._output_dir: Path | None = None
        self._stage = "idle"
        self._target_language = "en"
        self._build()
        self._refresh_hint()
        self._set_idle("把视频拖进来，或点击上方区域选择文件。")

    def open_full_mode(self) -> None:
        if self._busy:
            return
        existing = self._full_window
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        if self._settings is None or self._report is None:
            from localvideoai.app import _bootstrap

            self._settings, _database, self._report = _bootstrap()
        from localvideoai.app import _create_window

        window = _create_window(self._settings, self._report)
        self._full_window = window
        # A second window must not start GPU tasks alongside this one.
        self.player.pause()
        self._release_speech_model()
        self.hide()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(self._return_from_full_mode)
        window.show()
        recovered = window.prompt_unfinished_if_needed()
        if recovered is None and self._media is not None:
            window.add_video_path(self._media)

    def _return_from_full_mode(self) -> None:
        self._full_window = None
        self.show()

    def _build(self) -> None:
        from simplecaption.guided_ui import build_guided_ui
        build_guided_ui(self)

    def _combo(self, options: tuple[tuple[str, str], ...], current: str) -> QComboBox:
        box = QComboBox()
        box.setMinimumHeight(36)
        for label, value in options:
            box.addItem(label, value)
        index = box.findData(current)
        if index >= 0:
            box.setCurrentIndex(index)
        return box

    def _row(self, label: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        name = QLabel(label)
        name.setMinimumWidth(110)
        row.addWidget(name)
        row.addWidget(widget, 1)
        return row

    def _refresh_hint(self) -> None:
        quality = str(self.quality_combo.currentData() or "standard")
        self.hint.setText(context_hint_for(quality))

    def dragEnterEvent(self, event) -> None:
        if not self._busy and self._first_media_url(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        if self._busy:
            event.ignore()
            return
        path = self._first_media_url(event.mimeData().urls())
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.set_media(path)

    def _first_media_url(self, urls) -> Path | None:
        for url in urls:
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in _VIDEO_SUFFIXES:
                return path
        return None

    def _browse(self) -> None:
        if self._busy:
            return
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频",
            str(self._media.parent) if self._media else "",
            "视频 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.wmv *.flv *.ts *.m2ts *.mpeg *.mpg *.rmvb *.rm);;音频 (*.mp3 *.wav *.m4a *.aac *.flac)",
        )
        if chosen:
            self.set_media(Path(chosen))

    def set_media(self, path: Path) -> None:
        if self._busy:
            return
        source = path.expanduser()
        if not source.is_file():
            self._set_idle(f"找不到文件：{source}")
            return
        if source.suffix.lower() not in _VIDEO_SUFFIXES:
            self._set_idle("请选择视频或音频文件。")
            return
        self._media = source.resolve()
        self._output_dir = self._media.parent / f"{self._media.stem}_翻译结果" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._document = None
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.drop_label.setText(self._media.name)
        self.player.setSource(QUrl.fromLocalFile(str(self._media)))
        self._stage = "idle"
        self.stage_label.setText("已选择视频 · 下一步点击「开始翻译」")
        self._sync_buttons()
        self._set_idle(f"已选择：{self._media}")

    def start_transcription(self) -> None:
        if self._media is None or self._busy:
            self._set_idle("请先放入视频。")
            return
        if self._document is not None and self._document.segments:
            if QMessageBox.question(self, "重新识别", "重新识别会替换当前字幕。已保存的字幕文件会保留。继续吗？") != QMessageBox.StandardButton.Yes:
                self._pipeline = False
                return
        language = self.source_combo.currentData()
        self._set_busy(True)
        self.progress.setValue(0)
        self.status.setText(f"正在识别：{self._media.name}。请等待，完成后会提示下一步。")
        worker = TranscribeWorker(
            self._speech_engine(),
            self._media,
            None if language in {None, "auto"} else str(language),
            "auto",
            True,
            self,
            asr_batch_size=16,
            beam_size=1,
        )
        worker.progressChanged.connect(self._on_transcribe_progress)
        worker.succeeded.connect(self._on_transcribe_ok)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._transcribe_worker = worker
        self._stage = "recognizing"
        self.stage_label.setText("1 / 2 正在识别对白 · 完成后自动翻译" if self._pipeline else "正在识别对白")
        self._sync_buttons()
        worker.start()

    def start_translation(self) -> None:
        if self._document is None or self._busy:
            self._set_idle("请先完成语音识别。")
            return
        target = str(self.target_combo.currentData() or "en")
        source = str(self.source_combo.currentData() or "auto")
        quality = str(self.quality_combo.currentData() or "standard")
        self._set_busy(True)
        self.progress.setValue(0)
        self._release_speech_model()
        self.status.setText("正在翻译字幕，一次 32 句…")
        worker = TranslateWorker(
            self._translation_engine(),
            self._document,
            source,
            [target],
            quality,
            "auto",
            True,
            self,
            batch_size=32,
        )
        worker.progressChanged.connect(self._on_translate_progress)
        worker.succeeded.connect(self._on_translate_ok)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._translate_worker = worker
        self._stage = "translating"
        self.stage_label.setText("2 / 2 正在翻译 · 完成后请校对并导出")
        self._sync_buttons()
        worker.start()

    def show_document(self, document: SubtitleDocument) -> None:
        self._document = document
        self._fill_table()
        self._sync_buttons()

    def _speech_engine(self) -> FasterWhisperSpeechEngine:
        if self._speech is None:
            self._speech = FasterWhisperSpeechEngine()
        return self._speech

    def _release_speech_model(self) -> None:
        if self._speech is None:
            return
        self._speech.release()
        import gc

        gc.collect()

    def _translation_engine(self) -> CTranslate2TranslationEngine:
        if self._translation is None:
            self._translation = CTranslate2TranslationEngine()
        return self._translation

    def _on_transcribe_progress(self, current_ms: int, total_ms: int, message: str) -> None:
        self.progress.setValue(_percent(current_ms, total_ms))
        self.status.setText(message)

    def _on_translate_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setValue(_percent(current, total))
        self.status.setText(message)

    def _on_transcribe_ok(self, transcript) -> None:
        document = transcript_to_document(transcript)
        self.show_document(document)
        self.progress.setValue(100)
        saved = self._write_srt("source")
        extra = f" 原文字幕：{saved}" if saved else ""
        self.status.setText(
            f"识别完成：{len(document.segments)} 句，语言 {transcript.language}，"
            f"模型 {transcript.model_id}/{transcript.device}。{extra}"
        )
        self._translate_next = self._pipeline and bool(document.segments)
        if not document.segments:
            self._pipeline = False
            self._stage = "empty"
            self.stage_label.setText("没有识别到对白 · 可检查声音或进入高级工作站使用 OCR")

    def _on_translate_ok(self, document) -> None:
        self.show_document(document)
        self.progress.setValue(100)
        saved = self._write_srt("translated")
        count = sum(1 for item in document.segments if item.translated_text.strip())
        if saved:
            self.status.setText(f"翻译完成：{count} 句。请双击校对译文，再选择字幕或视频导出。自动备份：{saved}")
        else:
            self.status.setText(f"翻译完成：{count} 句。译文字幕没有写到视频旁边，请检查文件夹是否可写。")
        self._pipeline = False
        self._stage = "review"
        self.stage_label.setText("翻译结束 · 请检查是否有漏译，再导出；不会自动遮挡原画面")

    def _on_failed(self, message: str) -> None:
        self._pipeline = False
        self._translate_next = False
        self._stage = "failed"
        self._fill_table()
        self.stage_label.setText("处理失败 · 已有结果保留，可在当前步骤重试")
        self.progress.setValue(0)
        self.status.setText(message)

    def _on_worker_finished(self) -> None:
        self._set_busy(False)
        if self._translate_next:
            self._translate_next = False
            self.start_translation()
        elif self._stage == "recognizing":
            self._pipeline = False
            self.stage_label.setText("识别结束 · 点击「开始翻译」继续")

    def start_cover(self) -> None:
        if self._busy or self._media is None or self._document is None:
            self._set_idle("请先完成翻译。")
            return
        if not self._validate_translation():
            return
        if not any(item.translated_text.strip() for item in self._document.segments):
            self._set_idle("还没有译文，不能盖住原字幕。")
            return
        saved = self._write_srt("translated")
        if saved is None:
            return
        if self._media.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".flac"}:
            self.status.setText("音频只能导出字幕；请使用「保存译文字幕」。")
            return
        blur = self.blur_checkbox.isChecked()
        if blur and QMessageBox.question(self, "确认遮挡原字幕", "将对画面底部固定区域打马赛克，可能遮住人物或其他内容。这不是无痕去字幕。继续吗？") != QMessageBox.StandardButton.Yes:
            return
        suggested = self._output_dir / f"{self._media.stem}.translated.mp4"
        chosen, _ = QFileDialog.getSaveFileName(self, "导出带字幕的视频", str(suggested), "MP4 视频 (*.mp4)")
        if not chosen:
            return
        destination = Path(chosen).with_suffix(".mp4")
        if destination.resolve() == self._media.resolve():
            self.status.setText("请使用新文件名，不能覆盖原视频。")
            return
        if destination.exists() and QMessageBox.question(self, "替换导出文件", f"目标文件已存在：{destination.name}。替换它吗？") != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True)
        self.progress.setValue(0)
        self._stage = "exporting"
        self._sync_buttons()
        self.stage_label.setText("正在导出视频 · 此步骤可能较慢，请等待完成")
        self.status.setText("正在生成字幕视频；原视频保持不变。")
        from simplecaption.export_worker import VideoExportWorker
        worker = VideoExportWorker(self._media, saved, destination, blur=blur, parent=self)
        worker.progressChanged.connect(self._on_transcribe_progress)
        worker.succeeded.connect(self._on_cover_ok)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_cover_finished)
        self._cover_worker = worker
        worker.start()

    def _on_cover_ok(self, path) -> None:
        self.progress.setValue(100)
        self.stage_label.setText("视频导出成功")
        self.status.setText(f"字幕视频已保存：{path}")

    def _on_cover_finished(self) -> None:
        self._set_busy(False)

    def _write_srt(self, role: str) -> Path | None:
        if self._media is None or self._document is None:
            return None
        if role == "translated":
            lang = str(self.target_combo.currentData() or "target")
            destination = self._output_dir / f"{self._media.stem}.{lang}.srt"
        else:
            destination = self._output_dir / f"{self._media.stem}.source.srt"
        try:
            return save_role_srt(self._document, destination, role)
        except Exception as exc:
            self.status.setText(f"字幕已生成，但保存失败：{exc}")
            return None

    def _fill_table(self) -> None:
        document = self._document
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if document is None:
            self.table.blockSignals(False)
            return
        self.table.setRowCount(len(document.segments))
        for row, segment in enumerate(document.segments):
            values = (
                format_srt_timestamp(segment.start_time),
                format_srt_timestamp(segment.end_time),
                segment.display_text(),
                segment.translated_text,
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column < 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.player.pause()
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has_translation = self._document is not None and any(
            item.translated_text.strip() for item in self._document.segments
        )
        self.transcribe_button.setEnabled(self._media is not None and not self._busy)
        self.translate_button.setEnabled(self._document is not None and not self._busy)
        self.cover_button.setEnabled(self._media is not None and has_translation and not self._busy)
        self.source_combo.setEnabled(not self._busy)
        self.target_combo.setEnabled(not self._busy)
        self.quality_combo.setEnabled(not self._busy)
        self.start_button.setEnabled(self._media is not None and not self._busy)
        self.start_button.setText("② 重新翻译" if has_translation else "② 开始翻译")
        self.full_button.setEnabled(not self._busy)
        self.drop.setEnabled(not self._busy)
        self.table.setEnabled(not self._busy)
        self.export_button.setEnabled(has_translation and not self._busy)
        self.folder_button.setEnabled(self._output_dir is not None and self._output_dir.exists())
        self.blur_checkbox.setEnabled(not self._busy)
        self.stop_button.setVisible(self._busy and self._stage != "exporting")
        self.stop_button.setEnabled(self._pipeline)

    def _set_idle(self, message: str) -> None:
        self.status.setText(message)

    def start_pipeline(self) -> None:
        if self._busy or self._media is None:
            return
        if self._document is not None and self._document.segments:
            self.confirm_retranslation()
            return
        self._pipeline = True
        self.start_transcription()

    def confirm_retranslation(self) -> None:
        if self._busy or self._document is None:
            return
        if any(segment.translated_text.strip() for segment in self._document.segments):
            if QMessageBox.question(self, "重新翻译", "重新翻译会替换当前译文，包括人工修改。继续吗？") != QMessageBox.StandardButton.Yes:
                return
        self.start_translation()

    def stop_after_stage(self) -> None:
        self._pipeline = False
        self._translate_next = False
        self.stop_button.setEnabled(False)
        self.stage_label.setText("已安排停止 · 当前步骤仍在运行，完成后不进入下一步")

    def _target_changed(self) -> None:
        if self._document is not None:
            if any(segment.translated_text.strip() for segment in self._document.segments):
                try:
                    saved = self._output_dir / f"{self._media.stem}.{self._target_language}.srt"
                    save_role_srt(self._document, saved, "translated")
                except Exception as exc:
                    self.target_combo.blockSignals(True)
                    self.target_combo.setCurrentIndex(self.target_combo.findData(self._target_language))
                    self.target_combo.blockSignals(False)
                    self.status.setText(f"旧译文备份失败，未切换语言：{exc}")
                    return
            # Keep each language's saved file; clear only the current editor's translation.
            for segment in self._document.segments:
                segment.translated_text = ""
            self._fill_table()
            self.stage_label.setText("目标语言已切换 · 点击「开始翻译」生成新译文")
        self._target_language = str(self.target_combo.currentData())
        self._sync_buttons()

    def _source_changed(self) -> None:
        if self._busy:
            return
        if self._document is not None:
            self.status.setText("对白语言设置将在下次识别或翻译时使用；重新识别会先询问是否替换字幕。")

    def _on_caption_edited(self, item) -> None:
        if self._busy or self._document is None or item.row() >= len(self._document.segments):
            return
        segment = self._document.segments[item.row()]
        if item.column() == 2:
            segment.corrected_text = item.text()
            segment.source_text = item.text()
            segment.translated_text = ""
            self._fill_table()
            self.status.setText("原文已修改，该句旧译文已清空；请补填译文或重新翻译。")
        elif item.column() == 3:
            segment.translated_text = item.text()
            self.status.setText("译文已修改，请点击「保存译文字幕」保存，或导出字幕视频。")
        self._write_srt("source")
        self._write_srt("translated")
        self._sync_buttons()

    def seek_caption(self, row: int, column: int) -> None:
        if self._document is not None and row < len(self._document.segments):
            self.player.setPosition(self._document.segments[row].start_time)

    def toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def export_subtitles(self) -> None:
        if self._busy or not self._validate_translation():
            return
        suggested = self._output_dir / f"{self._media.stem}.{self.target_combo.currentData()}.srt"
        chosen, _ = QFileDialog.getSaveFileName(self, "保存校对后的译文字幕", str(suggested), "SRT 字幕 (*.srt)")
        if not chosen:
            return
        try:
            path = save_role_srt(self._document, Path(chosen).with_suffix(".srt"), "translated")
            self.status.setText(f"译文字幕已保存：{path}")
        except Exception as exc:
            self.status.setText(f"保存失败：{exc}")
        self._sync_buttons()

    def _validate_translation(self) -> bool:
        if self._document is None or not any(s.translated_text.strip() for s in self._document.segments):
            return False
        missing = sum(bool(s.display_text().strip()) and not s.translated_text.strip() for s in self._document.segments)
        if missing:
            self.status.setText(f"还有 {missing} 句没有译文，请在表格中补齐或重新翻译后导出。")
            return False
        return True

    def open_output_folder(self) -> None:
        if self._output_dir is not None and self._output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_dir)))

    def closeEvent(self, event) -> None:
        running = (
            (self._transcribe_worker is not None and self._transcribe_worker.isRunning())
            or (self._translate_worker is not None and self._translate_worker.isRunning())
            or (self._cover_worker is not None and self._cover_worker.isRunning())
        )
        if running:
            event.ignore()
            self.status.setText("正在处理，请等这一步结束再关闭。")
            return
        self.player.stop()
        super().closeEvent(event)


def _percent(current: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, int(current * 100 / total)))
