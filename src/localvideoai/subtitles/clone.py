from __future__ import annotations

from copy import deepcopy

from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument


def clone_segment(segment: SubtitleSegment) -> SubtitleSegment:
    return SubtitleSegment(
        id=segment.id,
        start_time=int(segment.start_time),
        end_time=int(segment.end_time),
        speaker=segment.speaker,
        source_text=segment.source_text,
        corrected_text=segment.corrected_text,
        translated_text=segment.translated_text,
        language=segment.language,
        confidence=segment.confidence,
        locked=segment.locked,
        style_id=segment.style_id,
        extra=deepcopy(segment.extra),
    )


def clone_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [clone_segment(item) for item in segments]


def replace_segments(document: SubtitleDocument, segments: list[SubtitleSegment]) -> SubtitleDocument:
    document.segments = segments
    return document
