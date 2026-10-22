"""Serialize subtitle documents inside task payloads so a reopen can resume."""

from __future__ import annotations

from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument


def document_to_dict(document: SubtitleDocument | None) -> dict | None:
    if document is None:
        return None
    return {
        "format_name": document.format_name or "srt",
        "detected_language": document.detected_language,
        "container_language": document.container_language,
        "quality_stage": document.quality_stage,
        "warnings": list(document.warnings),
        "segments": [_segment_to_dict(item) for item in document.segments],
    }


def document_from_dict(payload: dict | None) -> SubtitleDocument | None:
    if not payload:
        return None
    segments = [_segment_from_dict(item, index) for index, item in enumerate(payload.get("segments") or [], start=1)]
    return SubtitleDocument(
        segments=segments,
        format_name=str(payload.get("format_name") or "srt"),
        detected_language=str(payload.get("detected_language") or ""),
        container_language=str(payload.get("container_language") or ""),
        quality_stage=str(payload.get("quality_stage") or ""),
        warnings=list(payload.get("warnings") or []),
    )


def merge_documents(*documents: SubtitleDocument | None) -> SubtitleDocument:
    segments: list[SubtitleSegment] = []
    warnings: list[str] = []
    language = ""
    for document in documents:
        if document is None:
            continue
        segments.extend(document.segments)
        warnings.extend(document.warnings)
        language = language or document.detected_language
    ordered = sorted(segments, key=lambda item: (item.start_time, item.end_time, item.id))
    for index, segment in enumerate(ordered, start=1):
        segment.id = index
    return SubtitleDocument(
        segments=ordered,
        format_name="srt",
        detected_language=language,
        container_language=language,
        warnings=warnings,
    )


def _segment_to_dict(item: SubtitleSegment) -> dict:
    return {
        "id": item.id,
        "start_time": item.start_time,
        "end_time": item.end_time,
        "speaker": item.speaker,
        "source_text": item.source_text,
        "corrected_text": item.corrected_text,
        "translated_text": item.translated_text,
        "language": item.language,
        "confidence": item.confidence,
        "locked": item.locked,
        "style_id": item.style_id,
        "extra": dict(item.extra or {}),
    }


def _segment_from_dict(item: dict, fallback_id: int) -> SubtitleSegment:
    return SubtitleSegment(
        id=int(item.get("id") or fallback_id),
        start_time=int(item.get("start_time") or 0),
        end_time=int(item.get("end_time") or 0),
        speaker=str(item.get("speaker") or ""),
        source_text=str(item.get("source_text") or ""),
        corrected_text=str(item.get("corrected_text") or ""),
        translated_text=str(item.get("translated_text") or ""),
        language=str(item.get("language") or ""),
        confidence=item.get("confidence"),
        locked=bool(item.get("locked")),
        style_id=str(item.get("style_id") or ""),
        extra=dict(item.get("extra") or {}),
    )
