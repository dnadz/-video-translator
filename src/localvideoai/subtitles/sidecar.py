"""Full-fidelity extras beside SRT/ASS/VTT so lock / 原文 / 校正 / 译文 round-trip."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument

SCHEMA = 1
KIND = "localvideoai-subtitle-document"


def sidecar_path(subtitle_path: Path) -> Path:
    path = Path(subtitle_path)
    return path.with_name(path.name + ".lvai.json")


def segment_to_json(segment: SubtitleSegment) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": segment.id,
        "start_time": int(segment.start_time),
        "end_time": int(segment.end_time),
        "speaker": segment.speaker,
        "source_text": segment.source_text,
        "corrected_text": segment.corrected_text,
        "translated_text": segment.translated_text,
        "language": segment.language,
        "locked": bool(segment.locked),
        "style_id": segment.style_id,
        "extra": dict(segment.extra),
    }
    if segment.confidence is not None:
        payload["confidence"] = segment.confidence
    return payload


def segment_from_json(payload: dict[str, Any], fallback_id: int) -> SubtitleSegment:
    return SubtitleSegment(
        id=int(payload.get("id") or fallback_id),
        start_time=int(payload.get("start_time") or 0),
        end_time=int(payload.get("end_time") or 0),
        speaker=str(payload.get("speaker") or ""),
        source_text=str(payload.get("source_text") or ""),
        corrected_text=str(payload.get("corrected_text") or ""),
        translated_text=str(payload.get("translated_text") or ""),
        language=str(payload.get("language") or ""),
        confidence=payload.get("confidence"),
        locked=bool(payload.get("locked")),
        style_id=str(payload.get("style_id") or ""),
        extra=dict(payload.get("extra") or {}),
    )


def write_sidecar(document: SubtitleDocument, subtitle_path: Path) -> Path:
    destination = sidecar_path(subtitle_path)
    payload = {
        "schema": SCHEMA,
        "kind": KIND,
        "format_name": document.format_name,
        "detected_language": document.detected_language,
        "container_language": document.container_language,
        "speaker_map": dict(document.speaker_map),
        "speaker_styles": dict(document.speaker_styles),
        "quality_stage": document.quality_stage,
        "segments": [segment_to_json(item) for item in document.segments],
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def read_sidecar(subtitle_path: Path) -> dict[str, Any] | None:
    path = sidecar_path(subtitle_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SubtitleError(f"字幕附加文件不是有效 JSON：{path}") from exc
    if not isinstance(payload, dict):
        raise SubtitleError(f"字幕附加文件格式错误：{path}")
    return payload


def apply_sidecar(document: SubtitleDocument, subtitle_path: Path) -> SubtitleDocument:
    payload = read_sidecar(subtitle_path)
    if payload is None:
        return document
    raw_entries = payload.get("segments")
    if not isinstance(raw_entries, list):
        return document
    extras = [segment_from_json(item, index) for index, item in enumerate(raw_entries, start=1) if isinstance(item, dict)]
    if not extras:
        return document
    by_time = {(item.start_time, item.end_time): item for item in extras}
    restored: list[SubtitleSegment] = []
    for index, segment in enumerate(document.segments):
        match = by_time.get((segment.start_time, segment.end_time))
        if match is None and index < len(extras):
            candidate = extras[index]
            if candidate.start_time == segment.start_time and candidate.end_time == segment.end_time:
                match = candidate
        if match is None:
            restored.append(segment)
            continue
        segment.speaker = match.speaker or segment.speaker
        segment.source_text = match.source_text
        segment.corrected_text = match.corrected_text
        segment.translated_text = match.translated_text
        segment.language = match.language or segment.language
        segment.confidence = match.confidence if match.confidence is not None else segment.confidence
        segment.locked = match.locked
        segment.style_id = match.style_id or segment.style_id
        if match.extra:
            segment.extra = dict(match.extra)
        restored.append(segment)
    document.segments = restored
    if payload.get("detected_language") and not document.detected_language:
        document.detected_language = str(payload.get("detected_language") or "")
    raw_map = payload.get("speaker_map")
    if isinstance(raw_map, dict):
        document.speaker_map = {str(key): str(value) for key, value in raw_map.items() if str(key).strip()}
    raw_styles = payload.get("speaker_styles")
    if isinstance(raw_styles, dict):
        document.speaker_styles = {str(key): str(value) for key, value in raw_styles.items() if str(key).strip()}
    if payload.get("quality_stage"):
        document.quality_stage = str(payload.get("quality_stage") or "")
    return document
