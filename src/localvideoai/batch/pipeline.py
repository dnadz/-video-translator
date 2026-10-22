"""Run one video through analyze → speech → OCR → translate → review → export."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from localvideoai.batch.document import document_from_dict, document_to_dict, merge_documents
from localvideoai.batch.types import (
    STAGE_ANALYZE,
    STAGE_EXPORT,
    STAGE_OCR,
    STAGE_REVIEW,
    STAGE_SPEECH,
    STAGE_STATUS,
    STAGE_TRANSLATE,
    STAGES,
    STATUS_DONE,
    STATUS_FAIL,
    STATUS_PAUSE,
)
from localvideoai.core.exceptions import (
    ExportError,
    MediaError,
    OCRError,
    SpeechError,
    SubtitleError,
    TaskError,
    TranslationError,
)
from localvideoai.core.types import ExportRequest
from localvideoai.engines import create_export_engine
from localvideoai.export.subtitles import document_with_role
from localvideoai.ocr.persist import ocr_to_document
from localvideoai.speech.persist import transcript_to_document
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import save_subtitle

StopFn = Callable[[], bool]
PauseFn = Callable[[], bool]
PersistFn = Callable[..., dict[str, Any]]
ProgressFn = Callable[[str], None]


class BatchPipeline:
    def __init__(
        self,
        *,
        analyzer,
        speech_engine,
        ocr_engine,
        translation_engine,
        quality_engine,
        device: str = "auto",
        prefer_gpu: bool = True,
        source_lang: str = "auto",
        target_lang: str = "zh-CN",
        locks: dict[str, threading.Lock] | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._speech = speech_engine
        self._ocr = ocr_engine
        self._translation = translation_engine
        self._quality = quality_engine
        self.device = device
        self.prefer_gpu = prefer_gpu
        self.source_lang = source_lang
        self.target_lang = target_lang
        self._locks = locks or {name: threading.Lock() for name in STAGES}

    def process(
        self,
        task: dict[str, Any],
        *,
        persist: PersistFn,
        should_stop: StopFn,
        is_paused: PauseFn,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        task_id = str(task.get("id") or "")
        payload = dict(task.get("payload") or {})
        source = Path(str(payload.get("path") or "")).expanduser()
        if not source.is_file():
            return persist(status=STATUS_FAIL, error=f"视频不存在：{source}")
        done = [str(item) for item in payload.get("done_stages") or []]
        warnings = [str(item) for item in payload.get("warnings") or []]
        document = document_from_dict(payload.get("document"))
        speech_doc = document_from_dict(payload.get("speech_document"))
        ocr_doc = document_from_dict(payload.get("ocr_document"))

        for stage in STAGES:
            if stage in done:
                continue
            if should_stop():
                return persist(status=STATUS_FAIL, error="已取消", current_stage=stage)
            if is_paused():
                return persist(status=STATUS_PAUSE, current_stage=stage)
            persist(status=STAGE_STATUS[stage], current_stage=stage)
            if progress:
                progress(STAGE_STATUS[stage])
            try:
                if stage == STAGE_ANALYZE:
                    payload.update(self._analyze(source))
                elif stage == STAGE_SPEECH:
                    speech_doc, note = self._speech_stage(source, payload)
                    if note:
                        warnings.append(note)
                elif stage == STAGE_OCR:
                    ocr_doc, note = self._ocr_stage(source)
                    if note:
                        warnings.append(note)
                    document = merge_documents(speech_doc, ocr_doc)
                elif stage == STAGE_TRANSLATE:
                    document = document or merge_documents(speech_doc, ocr_doc)
                    note = self._translate_stage(document)
                    if note:
                        warnings.append(note)
                elif stage == STAGE_REVIEW:
                    document = document or merge_documents(speech_doc, ocr_doc)
                    payload.update(self._review_stage(document))
                elif stage == STAGE_EXPORT:
                    document = document or merge_documents(speech_doc, ocr_doc)
                    exported = self._export_stage(source, document)
                    payload["export_path"] = str(exported["export_path"])
                    if exported.get("export_video_path"):
                        payload["export_video_path"] = exported["export_video_path"]
            except (ExportError, MediaError, SpeechError, OCRError, TranslationError, SubtitleError, TaskError, OSError) as exc:
                return persist(
                    status=STATUS_FAIL,
                    error=str(exc),
                    current_stage=stage,
                    warnings=warnings,
                    document=document_to_dict(document),
                    speech_document=document_to_dict(speech_doc),
                    ocr_document=document_to_dict(ocr_doc),
                    done_stages=done,
                )
            done.append(stage)
            persist(
                status=STAGE_STATUS[stage],
                current_stage=stage,
                done_stages=list(done),
                warnings=warnings,
                document=document_to_dict(document),
                speech_document=document_to_dict(speech_doc),
                ocr_document=document_to_dict(ocr_doc),
                duration_ms=payload.get("duration_ms"),
                has_audio=payload.get("has_audio"),
                has_video=payload.get("has_video"),
                export_path=payload.get("export_path"),
                export_video_path=payload.get("export_video_path"),
                quality_score=payload.get("quality_score"),
                quality_issues=payload.get("quality_issues"),
            )

        return persist(
            status=STATUS_DONE,
            current_stage="",
            done_stages=list(done),
            warnings=warnings,
            document=document_to_dict(document),
            speech_document=document_to_dict(speech_doc),
            ocr_document=document_to_dict(ocr_doc),
            export_path=payload.get("export_path"),
            export_video_path=payload.get("export_video_path"),
            quality_score=payload.get("quality_score"),
            quality_issues=payload.get("quality_issues"),
            error="",
        )

    def _analyze(self, source: Path) -> dict[str, Any]:
        with self._locks[STAGE_ANALYZE]:
            analysis = self._analyzer.analyze(source)
        video = analysis.primary_video
        return {
            "duration_ms": analysis.duration_ms,
            "has_audio": bool(analysis.audio_tracks),
            "has_video": bool(analysis.video_tracks),
            "width": video.width if video else None,
            "height": video.height if video else None,
            "format_name": analysis.format_name,
        }

    def _speech_stage(self, source: Path, payload: dict[str, Any]) -> tuple[SubtitleDocument | None, str]:
        if not payload.get("has_audio"):
            return None, "无音轨，已跳过识别"
        try:
            with self._locks[STAGE_SPEECH]:
                transcript = self._speech.transcribe_media(
                    source,
                    language=None,
                    device_preference=self.device,
                    prefer_gpu=self.prefer_gpu,
                    save_raw=False,
                )
        except SpeechError as exc:
            return None, f"识别未产生可用字幕：{exc}"
        document = transcript_to_document(transcript)
        if not document.segments:
            return document, "识别完成，但没有可用语音文本"
        return document, ""

    def _ocr_stage(self, source: Path) -> tuple[SubtitleDocument | None, str]:
        try:
            with self._locks[STAGE_OCR]:
                transcript = self._ocr.recognize_video(
                    source,
                    language="zh",
                    device_preference=self.device,
                    prefer_gpu=self.prefer_gpu,
                    save_raw=False,
                )
        except OCRError as exc:
            message = str(exc)
            if "没有识别到" in message:
                return None, "OCR 未识别到硬字幕文字，继续后续阶段"
            raise
        document = ocr_to_document(transcript)
        if not document.segments:
            return document, "OCR 完成，但没有可用硬字幕"
        return document, ""

    def _translate_stage(self, document: SubtitleDocument) -> str:
        texts = [item.display_text().strip() for item in document.segments if item.display_text().strip()]
        if not texts:
            return "没有可翻译文本，已跳过翻译"
        with self._locks[STAGE_TRANSLATE]:
            self._translation.translate_document(
                document,
                self.source_lang,
                [self.target_lang],
                device_preference=self.device,
                prefer_gpu=self.prefer_gpu,
            )
        return ""

    def _review_stage(self, document: SubtitleDocument) -> dict[str, Any]:
        with self._locks[STAGE_REVIEW]:
            report = self._quality.inspect_document(document, apply_fixes=True)
        return {
            "quality_score": report.document_score,
            "quality_issues": report.issue_count,
            "quality_below_90": list(report.below_90),
        }

    def _export_stage(self, source: Path, document: SubtitleDocument) -> dict[str, str]:
        rendered = document
        if any(item.translated_text.strip() for item in document.segments):
            rendered = document_with_role(document, "translated")
        srt = self._write_srt(source, rendered)
        video = self._write_video(source, srt)
        result = {"export_path": str(srt)}
        if video is not None:
            result["export_video_path"] = str(video)
        return result

    def _write_srt(self, source: Path, document: SubtitleDocument) -> Path:
        dest = source.with_name(f"{source.stem}.zh.srt")
        try:
            with self._locks[STAGE_EXPORT]:
                return save_subtitle(document, dest, "srt")
        except (OSError, SubtitleError):
            fallback = source.parent / "batch_output" / f"{source.stem}.zh.srt"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with self._locks[STAGE_EXPORT]:
                return save_subtitle(document, fallback, "srt")

    def _write_video(self, source: Path, subtitle: Path) -> Path | None:
        dest = source.with_name(f"{source.stem}.zh.mp4")
        request = ExportRequest(
            video_path=source,
            subtitle_path=subtitle,
            output_path=dest,
            mode="embed",
            container="mp4",
            video_codec="copy",
            subtitle_format="srt",
        )
        try:
            with self._locks[STAGE_EXPORT]:
                return create_export_engine().export(request)
        except (OSError, ExportError):
            fallback = source.parent / "batch_output" / f"{source.stem}.zh.mp4"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            request = ExportRequest(
                video_path=source,
                subtitle_path=subtitle,
                output_path=fallback,
                mode="embed",
                container="mp4",
                video_codec="copy",
                subtitle_format="srt",
            )
            try:
                with self._locks[STAGE_EXPORT]:
                    return create_export_engine().export(request)
            except (OSError, ExportError):
                return None
