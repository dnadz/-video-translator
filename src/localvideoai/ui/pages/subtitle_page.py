from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.types import EmbeddedSubtitleTrack, SubtitleSegment
from localvideoai.quality.pipeline import next_issue_index
from localvideoai.quality.types import (
    BAND_LABELS,
    QualityReport,
    format_stage_pipeline,
)
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.editor import SubtitleEditor
from localvideoai.subtitles.language import language_display_name
from localvideoai.subtitles.timecodes import format_srt_timestamp, parse_timestamp
from localvideoai.ui import strings

BAND_COLORS = {
    "green": QColor(198, 239, 206),
    "yellow": QColor(255, 235, 156),
    "red": QColor(255, 199, 206),
}

COLUMNS = (
    ("id", "ID"),
    ("start_time", "开始"),
    ("end_time", "结束"),
    ("speaker", "说话人"),
    ("source_text", "原文"),
    ("corrected_text", "校正"),
    ("translated_text", "译文"),
    ("language", "语言"),
    ("confidence", "置信度"),
    ("locked", "锁定"),
    ("style_id", "样式"),
)

SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt"}


class SubtitlePage(QWidget):
    importClicked = Signal()
    saveClicked = Signal()
    saveAsClicked = Signal()
    filesDropped = Signal(list)
    previewEmbeddedClicked = Signal()
    extractEmbeddedClicked = Signal()
    documentChanged = Signal()
    cueSelected = Signal(int)
    statusMessage = Signal(str)
    findClicked = Signal()
    qualityCheckClicked = Signal()
    qualityJumpClicked = Signal()
    qualityConfirmClicked = Signal()
    qualityLockClicked = Signal()
    qualityFilterChanged = Signal(bool)
    issueActivated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("subtitlePage")
        self.setAcceptDrops(True)
        self._document: SubtitleDocument | None = None
        self._updating = False
        self._embedded_video: Path | None = None
        self._embedded_tracks: list[EmbeddedSubtitleTrack] = []
        self.editor = SubtitleEditor()
        self._filter_below_90 = False
        self._quality_report: QualityReport | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        self.hint = QLabel("导入 SRT / ASS / SSA / VTT，或从已打开视频提取内嵌字幕。表格使用统一内部格式 SubtitleSegment。")
        self.hint.setObjectName("subtitleHint")
        self.hint.setWordWrap(True)
        toolbar = QHBoxLayout()
        self.import_button = QPushButton("导入字幕")
        self.import_button.setObjectName("importSubtitleButton")
        self.save_button = QPushButton("保存字幕")
        self.save_button.setObjectName("saveSubtitleButton")
        self.save_as_button = QPushButton("字幕另存为")
        self.save_as_button.setObjectName("saveSubtitleAsButton")
        self.add_button = QPushButton("新增")
        self.add_button.setObjectName("addCueButton")
        self.delete_button = QPushButton("删除")
        self.delete_button.setObjectName("deleteCueButton")
        self.split_button = QPushButton("拆分")
        self.split_button.setObjectName("splitCueButton")
        self.merge_button = QPushButton("合并")
        self.merge_button.setObjectName("mergeCueButton")
        self.find_button = QPushButton("查找替换")
        self.find_button.setObjectName("findReplaceButton")
        self.undo_button = QPushButton("撤销")
        self.undo_button.setObjectName("undoSubtitleButton")
        self.redo_button = QPushButton("重做")
        self.redo_button.setObjectName("redoSubtitleButton")
        self.count_label = QLabel("0 条")
        self.count_label.setObjectName("subtitleCountLabel")
        self.import_button.clicked.connect(self.importClicked.emit)
        self.save_button.clicked.connect(self.saveClicked.emit)
        self.save_as_button.clicked.connect(self.saveAsClicked.emit)
        self.add_button.clicked.connect(lambda: self.add_cue())
        self.delete_button.clicked.connect(lambda: self.delete_selected())
        self.split_button.clicked.connect(lambda: self.split_selected())
        self.merge_button.clicked.connect(lambda: self.merge_selected())
        self.find_button.clicked.connect(self.findClicked.emit)
        self.undo_button.clicked.connect(lambda: self.undo())
        self.redo_button.clicked.connect(lambda: self.redo())
        for widget in (
            self.import_button,
            self.save_button,
            self.save_as_button,
            self.add_button,
            self.delete_button,
            self.split_button,
            self.merge_button,
            self.find_button,
            self.undo_button,
            self.redo_button,
        ):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        toolbar.addWidget(self.count_label)
        embedded = QHBoxLayout()
        embedded.addWidget(QLabel("内嵌轨道"))
        self.track_combo = QComboBox()
        self.track_combo.setObjectName("embeddedTrackCombo")
        self.track_combo.setMinimumWidth(280)
        self.preview_button = QPushButton("预览")
        self.preview_button.setObjectName("previewEmbeddedButton")
        self.extract_button = QPushButton("提取")
        self.extract_button.setObjectName("extractEmbeddedButton")
        self.preview_button.clicked.connect(self.previewEmbeddedClicked.emit)
        self.extract_button.clicked.connect(self.extractEmbeddedClicked.emit)
        embedded.addWidget(self.track_combo, 1)
        embedded.addWidget(self.preview_button)
        embedded.addWidget(self.extract_button)
        self.preview_box = QTextEdit()
        self.preview_box.setObjectName("embeddedPreviewBox")
        self.preview_box.setReadOnly(True)
        self.preview_box.setMaximumHeight(140)
        self.preview_box.hide()
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("subtitleTable")
        self.table.setHorizontalHeaderLabels([title for _, title in COLUMNS])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.quality_summary = QLabel("尚未做质量检查。识别 → 纠错 → 翻译 → 翻译审核 → QA → 人工确认 → 锁定")
        self.quality_summary.setObjectName("qualityScoreLabel")
        self.quality_summary.setWordWrap(True)
        quality_bar = QHBoxLayout()
        self.quality_button = QPushButton(strings.START_QUALITY_CHECK)
        self.quality_button.setObjectName("qualityCheckButton")
        self.filter_below_90 = QCheckBox(strings.FILTER_BELOW_90)
        self.filter_below_90.setObjectName("qualityBelow90Filter")
        self.jump_button = QPushButton(strings.JUMP_QUALITY_ISSUE)
        self.jump_button.setObjectName("qualityJumpButton")
        self.confirm_button = QPushButton(strings.CONFIRM_QUALITY)
        self.confirm_button.setObjectName("qualityConfirmButton")
        self.lock_confirmed_button = QPushButton(strings.LOCK_CONFIRMED)
        self.lock_confirmed_button.setObjectName("qualityLockButton")
        self.quality_button.clicked.connect(self.qualityCheckClicked.emit)
        self.filter_below_90.toggled.connect(self._on_filter_toggled)
        self.jump_button.clicked.connect(self.qualityJumpClicked.emit)
        self.confirm_button.clicked.connect(self.qualityConfirmClicked.emit)
        self.lock_confirmed_button.clicked.connect(self.qualityLockClicked.emit)
        for widget in (
            self.quality_button,
            self.filter_below_90,
            self.jump_button,
            self.confirm_button,
            self.lock_confirmed_button,
        ):
            quality_bar.addWidget(widget)
        quality_bar.addStretch(1)
        self.issue_list = QListWidget()
        self.issue_list.setObjectName("qualityIssueList")
        self.issue_list.setMaximumHeight(120)
        self.issue_list.itemActivated.connect(self._on_issue_activated)
        self.issue_list.itemClicked.connect(self._on_issue_activated)
        layout.addWidget(self.hint)
        layout.addLayout(toolbar)
        layout.addLayout(embedded)
        layout.addWidget(self.preview_box)
        layout.addWidget(self.quality_summary)
        layout.addLayout(quality_bar)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.issue_list)
        self.clear()
        self.set_embedded_tracks(None, [])

    @property
    def document(self) -> SubtitleDocument | None:
        return self._document

    @property
    def quality_report(self):
        return self._quality_report

    def clear(self) -> None:
        self._document = None
        self._quality_report = None
        self.editor.bind(None)
        self._updating = True
        self.table.setRowCount(0)
        self._updating = False
        self.count_label.setText("0 条")
        self.hint.setText("导入外部字幕，或从视频提取内嵌字幕。尚未打开字幕文件。")
        self.quality_summary.setText("尚未做质量检查。识别 → 纠错 → 翻译 → 翻译审核 → QA → 人工确认 → 锁定")
        self.issue_list.clear()
        self.documentChanged.emit()

    def set_library_count(self, count: int) -> None:
        extra = f"项目中记录了 {count} 个字幕文件。" if count else "项目中还没有字幕文件。"
        if self._document is None:
            self.hint.setText(f"导入外部字幕，或从视频提取内嵌字幕。{extra}")

    @property
    def embedded_video_path(self) -> Path | None:
        return self._embedded_video

    def embedded_tracks(self) -> list[EmbeddedSubtitleTrack]:
        return list(self._embedded_tracks)

    def selected_embedded_track(self) -> EmbeddedSubtitleTrack | None:
        data = self.track_combo.currentData()
        return data if isinstance(data, EmbeddedSubtitleTrack) else None

    def set_embedded_tracks(self, video_path: Path | None, tracks: list[EmbeddedSubtitleTrack]) -> None:
        self._embedded_video = video_path
        self._embedded_tracks = list(tracks)
        self.track_combo.blockSignals(True)
        self.track_combo.clear()
        for track in tracks:
            lang = language_display_name(track.language)
            self.track_combo.addItem(f"{track.label()}（{lang}）", track)
        self.track_combo.blockSignals(False)
        has_tracks = bool(tracks)
        self.track_combo.setEnabled(has_tracks)
        self.preview_button.setEnabled(has_tracks)
        self.extract_button.setEnabled(has_tracks)
        if not has_tracks:
            self.preview_box.hide()
            self.preview_box.clear()
            if video_path is None:
                self.track_combo.addItem("先打开视频以列出内嵌字幕")
            else:
                self.track_combo.addItem("当前视频没有内嵌字幕轨道")

    def show_preview(self, document: SubtitleDocument, track: EmbeddedSubtitleTrack) -> None:
        lang = language_display_name(document.detected_language or track.language)
        lines = [
            f"轨道 #{track.index}  {language_display_name(track.language)}  {track.format_name}",
            f"容器语言：{track.container_language or 'und'}  识别语言：{lang}",
            f"预览 {len(document.segments)} 条（内部格式 SubtitleSegment）",
            "",
        ]
        for segment in document.segments:
            lines.append(
                f"{segment.id}  {format_srt_timestamp(segment.start_time)} --> "
                f"{format_srt_timestamp(segment.end_time)}"
            )
            lines.append(segment.source_text or "（空）")
            lines.append("")
        if document.warnings:
            lines.append("警告：")
            lines.extend(document.warnings[:12])
        self.preview_box.setPlainText("\n".join(lines).strip())
        self.preview_box.show()

    def show_extract_error(self, message: str) -> None:
        self.preview_box.setPlainText(message)
        self.preview_box.show()
        self.hint.setText(message)

    def set_document(self, document: SubtitleDocument, *, reset_history: bool = True) -> None:
        self._document = document
        if reset_history:
            self.editor.bind(document)
        else:
            self.editor.document = document
        self.refresh_table()
        warnings = f" 警告 {len(document.warnings)} 条。" if document.warnings else ""
        name = document.source_path.name if document.source_path else "未保存"
        self.hint.setText(f"正在编辑：{name}（{document.format_name.upper()}，{len(document.segments)} 条）。{warnings}".strip())
        if document.warnings:
            self.hint.setToolTip("\n".join(document.warnings[:40]))
        else:
            self.hint.setToolTip("")
        self.documentChanged.emit()

    def refresh_table(self) -> None:
        document = self._document
        self._updating = True
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            if document is None:
                self.count_label.setText("0 条")
                return
            self.table.setRowCount(len(document.segments))
            for row, segment in enumerate(document.segments):
                self._write_row(row, segment)
                self._apply_row_filter(row, segment)
            self.count_label.setText(self._count_label_text(document))
            self._refresh_issue_list()
            self._update_quality_summary()
        finally:
            self.table.setUpdatesEnabled(True)
            self._updating = False

    def current_segments(self) -> list[SubtitleSegment]:
        if self._document is None:
            return []
        return list(self._document.segments)

    def selected_indexes(self) -> list[int]:
        rows = sorted({item.row() for item in self.table.selectedItems()} | {index.row() for index in self.table.selectedIndexes()})
        if self._document is None:
            return []
        return [row for row in rows if 0 <= row < len(self._document.segments)]

    def select_row(self, row: int) -> None:
        if self._document is None or not (0 <= row < len(self._document.segments)):
            return
        self.table.selectRow(row)
        item = self.table.item(row, 4)
        if item is not None:
            self.table.scrollToItem(item)

    def apply_text_edit(self, segment_id: int, field: str, value: str) -> None:
        if self._document is None:
            return
        for index, segment in enumerate(self._document.segments):
            if segment.id == segment_id:
                self._run(lambda: self.editor.modify(index, field, value))
                return

    def add_cue(self, start_ms: int = 0, source_text: str = "") -> None:
        if self._document is None:
            self.set_document(SubtitleDocument(segments=[], format_name="srt"))
        playhead = int(start_ms) if start_ms else 0
        if not playhead and self._document and self._document.segments:
            playhead = self._document.segments[-1].end_time
        self._run(lambda: self.editor.add(playhead, source_text=source_text or "新字幕"))

    def delete_selected(self) -> None:
        indexes = self.selected_indexes()
        if not indexes:
            self.statusMessage.emit("请先选择要删除的字幕")
            return
        self._run(lambda: self.editor.delete(indexes))

    def split_selected(self, at_ms: int | None = None) -> None:
        indexes = self.selected_indexes()
        if len(indexes) != 1:
            self.statusMessage.emit("请选择一条字幕再拆分")
            return
        self._run(lambda: self.editor.split(indexes[0], at_ms))

    def merge_selected(self) -> None:
        indexes = self.selected_indexes()
        if len(indexes) < 2:
            self.statusMessage.emit("请选择至少两条连续字幕再合并")
            return
        self._run(lambda: self.editor.merge(indexes))

    def undo(self) -> None:
        if self.editor.undo():
            self.refresh_table()
            self.documentChanged.emit()
        else:
            self.statusMessage.emit("没有可撤销的编辑")

    def redo(self) -> None:
        if self.editor.redo():
            self.refresh_table()
            self.documentChanged.emit()
        else:
            self.statusMessage.emit("没有可重做的编辑")

    def _run(self, action) -> None:
        try:
            action()
        except SubtitleError as exc:
            self.statusMessage.emit(str(exc))
            return
        self.refresh_table()
        self.documentChanged.emit()

    def _write_row(self, row: int, segment: SubtitleSegment) -> None:
        values = [
            str(segment.id),
            format_srt_timestamp(segment.start_time),
            format_srt_timestamp(segment.end_time),
            segment.speaker,
            segment.source_text,
            segment.corrected_text,
            segment.translated_text,
            segment.language,
            "" if segment.confidence is None else str(segment.confidence),
            "1" if segment.locked else "0",
            segment.style_id,
        ]
        for column, value in enumerate(values):
            if column == 9:
                box = QCheckBox()
                box.setObjectName(f"subtitleLocked_{row}")
                box.blockSignals(True)
                box.setChecked(segment.locked)
                box.blockSignals(False)
                box.stateChanged.connect(lambda state, r=row: self._on_locked(r, state))
                self.table.setCellWidget(row, column, box)
                continue
            item = QTableWidgetItem(value)
            if column == 0:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if segment.locked and column not in {0, 9}:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, item)
        self._color_row(row, segment)

    def _on_locked(self, row: int, state: int) -> None:
        if self._updating or self._document is None or not (0 <= row < len(self._document.segments)):
            return
        try:
            self.editor.modify(row, "locked", bool(state))
        except SubtitleError as exc:
            self.statusMessage.emit(str(exc))
            return
        self.refresh_table()
        self.documentChanged.emit()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None:
            return
        row = item.row()
        column = item.column()
        if not (0 <= row < len(self._document.segments)):
            return
        segment = self._document.segments[row]
        key = COLUMNS[column][0]
        text = item.text()
        try:
            if key in {"start_time", "end_time"}:
                value: object = parse_timestamp(text)
            elif key == "confidence":
                value = None if text.strip() == "" else float(text)
            elif key == "id":
                return
            else:
                value = text
            if key in {"start_time", "end_time"} and int(value) == getattr(segment, key):
                return
            if key not in {"start_time", "end_time", "confidence"} and text == getattr(segment, key):
                return
            self.editor.modify(row, key, value)
        except (SubtitleError, ValueError):
            self._updating = True
            if key in {"start_time", "end_time"}:
                item.setText(format_srt_timestamp(getattr(segment, key)))
            self._updating = False
            return
        self.refresh_table()
        self.documentChanged.emit()

    def _on_selection_changed(self) -> None:
        indexes = self.selected_indexes()
        if indexes:
            self.cueSelected.emit(indexes[0])
            self._update_quality_summary()

    def apply_quality_report(self, report: QualityReport) -> None:
        self._quality_report = report
        self.refresh_table()

    def set_filter_below_90(self, enabled: bool) -> None:
        if self.filter_below_90.isChecked() != enabled:
            self.filter_below_90.setChecked(enabled)
            return
        self._filter_below_90 = enabled
        if self._document is not None:
            for row, segment in enumerate(self._document.segments):
                self._apply_row_filter(row, segment)

    def next_issue_row(self) -> int | None:
        if self._document is None:
            return None
        current = self.selected_indexes()[0] if self.selected_indexes() else -1
        return next_issue_index(self._document, current)

    def _on_filter_toggled(self, checked: bool) -> None:
        self._filter_below_90 = checked
        if self._document is not None:
            for row, segment in enumerate(self._document.segments):
                self._apply_row_filter(row, segment)
        self.qualityFilterChanged.emit(checked)

    def _on_issue_activated(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self.select_row(index)
            self.issueActivated.emit(index)

    def _qa_payload(self, segment: SubtitleSegment) -> dict:
        payload = segment.extra.get("qa") if isinstance(segment.extra, dict) else {}
        return payload if isinstance(payload, dict) else {}

    def _color_row(self, row: int, segment: SubtitleSegment) -> None:
        band = str(self._qa_payload(segment).get("band") or "")
        color = BAND_COLORS.get(band)
        if color is None:
            return
        brush = QBrush(color)
        for column in range(len(COLUMNS)):
            item = self.table.item(row, column)
            if item is not None:
                item.setBackground(brush)

    def _apply_row_filter(self, row: int, segment: SubtitleSegment) -> None:
        payload = self._qa_payload(segment)
        if not self._filter_below_90 or "composite" not in payload:
            self.table.setRowHidden(row, False)
            return
        try:
            score = float(payload.get("composite", 100.0))
        except (TypeError, ValueError):
            score = 100.0
        self.table.setRowHidden(row, score >= 90)

    def _count_label_text(self, document: SubtitleDocument) -> str:
        total = len(document.segments)
        if self._quality_report is None:
            return f"{total} 条"
        return f"{total} 条 · {len(self._quality_report.below_90)} 条低于90 · {self._quality_report.issue_count} 个问题"

    def _refresh_issue_list(self) -> None:
        self.issue_list.clear()
        document = self._document
        if document is None:
            return
        for index, segment in enumerate(document.segments):
            payload = self._qa_payload(segment)
            issues = payload.get("issues") or []
            if not isinstance(issues, list):
                continue
            score = payload.get("composite")
            band = BAND_LABELS.get(str(payload.get("band") or ""), "")
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                message = str(issue.get("message") or issue.get("code") or "问题")
                suffix = f" · 综合 {score}" if score is not None else ""
                label = f"#{segment.id} {message}{suffix}"
                if band:
                    label = f"{label} · {band}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.issue_list.addItem(item)

    def _update_quality_summary(self) -> None:
        document = self._document
        if document is None:
            self.quality_summary.setText("尚未做质量检查。识别 → 纠错 → 翻译 → 翻译审核 → QA → 人工确认 → 锁定")
            return
        stage = format_stage_pipeline(document.quality_stage)
        selected = self.selected_indexes()
        if not selected:
            doc_score = self._quality_report.document_score if self._quality_report is not None else None
            extra = f" 文档综合 {doc_score}。" if doc_score is not None else ""
            self.quality_summary.setText(f"{stage}{extra}".strip())
            return
        payload = self._qa_payload(document.segments[selected[0]])
        if "composite" not in payload:
            self.quality_summary.setText(f"{stage}  当前条尚未评分。")
            return
        band = str(payload.get("band") or "")
        label = BAND_LABELS.get(band, "")
        confirmed = "已确认" if payload.get("confirmed") else "未确认"
        locked = "已锁定" if document.segments[selected[0]].locked else "未锁定"
        self.quality_summary.setText(
            f"{stage}\n"
            f"识别置信度 {payload.get('recognition')}  翻译评分 {payload.get('translation')}  "
            f"上下文一致性 {payload.get('consistency')}  综合评分 {payload.get('composite')}（{label}）  "
            f"{confirmed} / {locked}"
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local and Path(local).suffix.lower() in SUBTITLE_EXTENSIONS:
                paths.append(local)
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
        else:
            event.ignore()
