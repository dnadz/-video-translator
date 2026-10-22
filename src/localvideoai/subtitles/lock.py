"""Keep human-locked cues when AI produces a replacement document."""

from __future__ import annotations

from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.clone import clone_segment
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import assign_ids


def ranges_overlap(left: SubtitleSegment, right: SubtitleSegment) -> bool:
    return left.start_time < right.end_time and right.start_time < left.end_time


def preserve_locked(current: SubtitleDocument | None, incoming: SubtitleDocument) -> SubtitleDocument:
    if current is None:
        return incoming
    locked = [clone_segment(item) for item in current.segments if item.locked]
    if not locked:
        return incoming
    kept = [item for item in incoming.segments if not any(ranges_overlap(item, hold) for hold in locked)]
    incoming.segments = assign_ids(kept + locked)
    incoming.warnings = list(incoming.warnings)
    incoming.warnings.append(f"保留 {len(locked)} 条人工锁定字幕，AI 结果未覆盖。")
    return incoming
