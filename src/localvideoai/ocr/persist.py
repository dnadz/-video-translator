from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from localvideoai.core.paths import ensure_directory, ocr_results_dir
from localvideoai.core.types import OCRCue, OCRTranscript, SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument


def save_ocr_transcript(transcript: OCRTranscript, destination: Path | None = None) -> Path:
    dest = destination or _default_path(transcript)
    ensure_directory(dest.parent)
    payload = {
        "schema": 1,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(transcript.source_path),
        "language": transcript.language,
        "model_id": transcript.model_id,
        "device": transcript.device,
        "region": list(transcript.region),
        "region_source": transcript.region_source,
        "duration_ms": transcript.duration_ms,
        "frames_decoded": transcript.frames_decoded,
        "frames_ocr": transcript.frames_ocr,
        "warnings": list(transcript.warnings),
        "cues": [_cue_dict(item) for item in transcript.cues],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    transcript.raw_path = dest
    return dest


def ocr_to_document(transcript: OCRTranscript) -> SubtitleDocument:
    segments: list[SubtitleSegment] = []
    for index, item in enumerate(transcript.cues, start=1):
        segments.append(
            SubtitleSegment(
                id=index,
                start_time=item.start_ms,
                end_time=item.end_ms,
                source_text=item.text,
                language=item.language or transcript.language,
                confidence=item.confidence,
                extra={"ocr": {"x": item.x, "y": item.y, "w": item.w, "h": item.h}},
            )
        )
    return SubtitleDocument(
        segments=segments,
        format_name="srt",
        detected_language=transcript.language,
        container_language=transcript.language,
    )


def _cue_dict(item: OCRCue) -> dict:
    return {
        "start_ms": item.start_ms,
        "end_ms": item.end_ms,
        "text": item.text,
        "confidence": item.confidence,
        "language": item.language,
        "x": item.x,
        "y": item.y,
        "w": item.w,
        "h": item.h,
        "boxes": [
            {
                "start_ms": box.start_ms,
                "end_ms": box.end_ms,
                "text": box.text,
                "confidence": box.confidence,
                "points": [list(point) for point in box.points],
            }
            for box in item.boxes
        ],
    }


def _default_path(transcript: OCRTranscript) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = transcript.source_path.stem or "ocr"
    return ocr_results_dir() / f"{name}-{stamp}.json"
