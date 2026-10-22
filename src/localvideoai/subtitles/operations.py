"""Pure subtitle list operations. No Qt. Times are integer milliseconds."""

from __future__ import annotations

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.clone import clone_segment
from localvideoai.subtitles.io import assign_ids

MIN_DURATION_MS = 40
DEFAULT_DURATION_MS = 1000
TEXT_FIELDS = ("source_text", "corrected_text", "translated_text")


def clamp_range(start_ms: int, end_ms: int) -> tuple[int, int]:
    start = max(0, int(start_ms))
    end = max(start + MIN_DURATION_MS, int(end_ms))
    return start, end


def add_cue(
    segments: list[SubtitleSegment],
    *,
    start_ms: int,
    duration_ms: int = DEFAULT_DURATION_MS,
    source_text: str = "",
) -> list[SubtitleSegment]:
    start, end = clamp_range(start_ms, start_ms + max(MIN_DURATION_MS, duration_ms))
    created = SubtitleSegment(id=0, start_time=start, end_time=end, source_text=source_text)
    return assign_ids([*segments, created])


def delete_cues(segments: list[SubtitleSegment], indexes: list[int]) -> list[SubtitleSegment]:
    drop = {int(index) for index in indexes}
    remaining = [item for index, item in enumerate(segments) if index not in drop]
    if len(remaining) == len(segments):
        raise SubtitleError("没有可删除的字幕")
    return assign_ids(remaining)


def modify_field(segment: SubtitleSegment, field: str, value: object) -> SubtitleSegment:
    if field in {"start_time", "end_time"}:
        start = int(value) if field == "start_time" else segment.start_time
        end = int(value) if field == "end_time" else segment.end_time
        start, end = clamp_range(start, end)
        segment.start_time = start
        segment.end_time = end
        return segment
    if field == "locked":
        segment.locked = bool(value)
        return segment
    if field == "confidence":
        if value is None or value == "":
            segment.confidence = None
        else:
            segment.confidence = float(value)
        return segment
    if not hasattr(segment, field) or field in {"id", "extra"}:
        raise SubtitleError(f"不能修改字段：{field}")
    setattr(segment, field, value)
    return segment


def move_cue(segment: SubtitleSegment, delta_ms: int) -> SubtitleSegment:
    if segment.locked:
        raise SubtitleError("已锁定的字幕不能拖动时间")
    delta = int(delta_ms)
    duration = max(MIN_DURATION_MS, segment.end_time - segment.start_time)
    start = max(0, segment.start_time + delta)
    segment.start_time = start
    segment.end_time = start + duration
    return segment


def resize_cue(segment: SubtitleSegment, *, start_ms: int | None = None, end_ms: int | None = None) -> SubtitleSegment:
    if segment.locked:
        raise SubtitleError("已锁定的字幕不能调整时间")
    start = segment.start_time if start_ms is None else int(start_ms)
    end = segment.end_time if end_ms is None else int(end_ms)
    segment.start_time, segment.end_time = clamp_range(start, end)
    return segment


def split_text(text: str) -> tuple[str, str]:
    blob = text or ""
    if "\n" in blob:
        left, right = blob.split("\n", 1)
        return left, right
    stripped = blob.strip()
    if not stripped:
        return "", ""
    mid = max(1, len(blob) // 2)
    split_at = blob.rfind(" ", 0, mid + 1)
    if split_at <= 0:
        split_at = mid
    return blob[:split_at].rstrip(), blob[split_at:].lstrip()


def split_cue(segment: SubtitleSegment, at_ms: int | None = None) -> tuple[SubtitleSegment, SubtitleSegment]:
    if segment.locked:
        raise SubtitleError("已锁定的字幕不能拆分")
    start, end = clamp_range(segment.start_time, segment.end_time)
    span = end - start
    if span < MIN_DURATION_MS * 2:
        raise SubtitleError("字幕太短，无法拆分")
    cut = start + span // 2 if at_ms is None else int(at_ms)
    cut = min(end - MIN_DURATION_MS, max(start + MIN_DURATION_MS, cut))
    left = clone_segment(segment)
    right = clone_segment(segment)
    left.end_time = cut
    right.start_time = cut
    left.source_text, right.source_text = split_text(segment.source_text)
    left.corrected_text, right.corrected_text = split_text(segment.corrected_text)
    left.translated_text, right.translated_text = split_text(segment.translated_text)
    return left, right


def split_at(segments: list[SubtitleSegment], index: int, at_ms: int | None = None) -> list[SubtitleSegment]:
    if not (0 <= index < len(segments)):
        raise SubtitleError("没有选中要拆分的字幕")
    left, right = split_cue(segments[index], at_ms)
    return assign_ids([*segments[:index], left, right, *segments[index + 1 :]])


def merge_cues(parts: list[SubtitleSegment]) -> SubtitleSegment:
    if len(parts) < 2:
        raise SubtitleError("合并至少需要两条字幕")
    if any(item.locked for item in parts):
        raise SubtitleError("已锁定的字幕不能合并")
    ordered = sorted(parts, key=lambda item: (item.start_time, item.end_time, item.id))
    merged = clone_segment(ordered[0])
    merged.end_time = max(item.end_time for item in ordered)
    merged.start_time, merged.end_time = clamp_range(min(item.start_time for item in ordered), merged.end_time)
    merged.source_text = "\n".join(item.source_text for item in ordered if item.source_text).strip()
    merged.corrected_text = "\n".join(item.corrected_text for item in ordered if item.corrected_text).strip()
    merged.translated_text = "\n".join(item.translated_text for item in ordered if item.translated_text).strip()
    speakers = [item.speaker for item in ordered if item.speaker]
    merged.speaker = speakers[0] if len(set(speakers)) == 1 else (speakers[0] if speakers else "")
    return merged


def merge_indexes(segments: list[SubtitleSegment], indexes: list[int]) -> list[SubtitleSegment]:
    unique = sorted({int(index) for index in indexes})
    if len(unique) < 2:
        raise SubtitleError("请选择至少两条字幕再合并")
    if unique != list(range(unique[0], unique[-1] + 1)):
        raise SubtitleError("只能合并连续的字幕")
    parts = [segments[index] for index in unique]
    merged = merge_cues(parts)
    return assign_ids([*segments[: unique[0]], merged, *segments[unique[-1] + 1 :]])


def find_matches(segments: list[SubtitleSegment], needle: str, fields: tuple[str, ...] = TEXT_FIELDS) -> list[tuple[int, str]]:
    text = needle or ""
    if not text:
        return []
    hits: list[tuple[int, str]] = []
    for index, segment in enumerate(segments):
        for field in fields:
            blob = getattr(segment, field, "") or ""
            if text in blob:
                hits.append((index, field))
    return hits


def replace_matches(
    segments: list[SubtitleSegment],
    needle: str,
    replacement: str,
    fields: tuple[str, ...] = TEXT_FIELDS,
    *,
    indexes: list[int] | None = None,
    skip_locked: bool = True,
) -> int:
    if not needle:
        return 0
    allowed = None if indexes is None else set(indexes)
    changed = 0
    for index, segment in enumerate(segments):
        if allowed is not None and index not in allowed:
            continue
        if skip_locked and segment.locked:
            continue
        for field in fields:
            blob = getattr(segment, field, "") or ""
            if needle not in blob:
                continue
            setattr(segment, field, blob.replace(needle, replacement))
            changed += 1
    return changed
