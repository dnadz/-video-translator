from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from localvideoai.core.paths import ensure_directory, transcripts_dir
from localvideoai.core.types import SpeechTranscript, SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument


def save_transcript(transcript: SpeechTranscript, destination: Path | None = None) -> Path:
    dest = destination or _default_path(transcript)
    ensure_directory(dest.parent)
    payload = {
        "schema": 1,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(transcript.source_path),
        "language": transcript.language,
        "language_probability": transcript.language_probability,
        "model_id": transcript.model_id,
        "device": transcript.device,
        "compute_type": transcript.compute_type,
        "duration_ms": transcript.duration_ms,
        "chunk_count": transcript.chunk_count,
        "warnings": list(transcript.warnings),
        "segments": [_segment_dict(item) for item in transcript.segments],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    transcript.raw_path = dest
    return dest


def transcript_to_document(transcript: SpeechTranscript) -> SubtitleDocument:
    segments: list[SubtitleSegment] = []
    for index, item in enumerate(transcript.segments, start=1):
        segments.append(
            SubtitleSegment(
                id=index,
                start_time=item.start_ms,
                end_time=item.end_ms,
                source_text=item.text,
                speaker=item.speaker or "",
                language=item.language or transcript.language,
                confidence=item.confidence,
            )
        )
    return SubtitleDocument(
        segments=segments,
        format_name="srt",
        detected_language=transcript.language,
        container_language=transcript.language,
    )


def _segment_dict(item) -> dict:
    return {
        "start_ms": item.start_ms,
        "end_ms": item.end_ms,
        "text": item.text,
        "confidence": item.confidence,
        "speaker": item.speaker,
        "language": item.language,
        "words": [
            {
                "start_ms": word.start_ms,
                "end_ms": word.end_ms,
                "text": word.text,
                "confidence": word.confidence,
            }
            for word in item.words
        ],
    }


def _default_path(transcript: SpeechTranscript) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = transcript.source_path.stem or "transcript"
    return transcripts_dir() / f"{name}-{stamp}.json"
