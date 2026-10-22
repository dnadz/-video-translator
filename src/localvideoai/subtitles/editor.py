"""Undoable subtitle document editor. UI must go through this, not mutate rows ad hoc."""

from __future__ import annotations

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.clone import clone_segments
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.operations import (
    TEXT_FIELDS,
    add_cue,
    delete_cues,
    find_matches,
    merge_indexes,
    modify_field,
    move_cue,
    replace_matches,
    resize_cue,
    split_at,
)

MAX_HISTORY = 80


class SubtitleEditor:
    def __init__(self) -> None:
        self.document: SubtitleDocument | None = None
        self._undo: list[list[SubtitleSegment]] = []
        self._redo: list[list[SubtitleSegment]] = []
        self._gesture: list[SubtitleSegment] | None = None

    def bind(self, document: SubtitleDocument | None) -> None:
        self.document = document
        self._undo.clear()
        self._redo.clear()
        self._gesture = None

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if self.document is None or not self._undo:
            return False
        self._redo.append(clone_segments(self.document.segments))
        self.document.segments = self._undo.pop()
        return True

    def redo(self) -> bool:
        if self.document is None or not self._redo:
            return False
        self._undo.append(clone_segments(self.document.segments))
        self.document.segments = self._redo.pop()
        return True

    def begin_gesture(self) -> None:
        if self.document is None:
            return
        self._gesture = clone_segments(self.document.segments)

    def end_gesture(self) -> None:
        if self.document is None or self._gesture is None:
            self._gesture = None
            return
        if _same_times_and_text(self._gesture, self.document.segments):
            self._gesture = None
            return
        self._undo.append(self._gesture)
        self._trim()
        self._redo.clear()
        self._gesture = None

    def add(self, start_ms: int, source_text: str = "", duration_ms: int = 1000) -> SubtitleSegment:
        document = self._require()
        self._push()
        document.segments = add_cue(document.segments, start_ms=start_ms, duration_ms=duration_ms, source_text=source_text)
        return document.segments[-1]

    def delete(self, indexes: list[int]) -> None:
        document = self._require()
        for index in indexes:
            if 0 <= index < len(document.segments) and document.segments[index].locked:
                raise SubtitleError("已锁定的字幕不能删除，请先解锁")
        self._push()
        document.segments = delete_cues(document.segments, indexes)

    def modify(self, index: int, field: str, value: object) -> None:
        document = self._require()
        if not (0 <= index < len(document.segments)):
            raise SubtitleError("没有选中的字幕")
        segment = document.segments[index]
        if segment.locked and field != "locked":
            raise SubtitleError("已锁定的字幕不能修改，请先解锁")
        self._push()
        modify_field(segment, field, value)

    def split(self, index: int, at_ms: int | None = None) -> None:
        document = self._require()
        self._push()
        document.segments = split_at(document.segments, index, at_ms)

    def merge(self, indexes: list[int]) -> None:
        document = self._require()
        self._push()
        document.segments = merge_indexes(document.segments, indexes)

    def move(self, index: int, delta_ms: int) -> None:
        document = self._require()
        if not (0 <= index < len(document.segments)):
            raise SubtitleError("没有选中的字幕")
        if self._gesture is None:
            self._push()
        move_cue(document.segments[index], delta_ms)

    def resize(self, index: int, *, start_ms: int | None = None, end_ms: int | None = None) -> None:
        document = self._require()
        if not (0 <= index < len(document.segments)):
            raise SubtitleError("没有选中的字幕")
        if self._gesture is None:
            self._push()
        resize_cue(document.segments[index], start_ms=start_ms, end_ms=end_ms)

    def find(self, needle: str, fields: tuple[str, ...] = TEXT_FIELDS) -> list[tuple[int, str]]:
        document = self._require()
        return find_matches(document.segments, needle, fields)

    def replace(self, needle: str, replacement: str, fields: tuple[str, ...] = TEXT_FIELDS) -> int:
        document = self._require()
        self._push()
        changed = replace_matches(document.segments, needle, replacement, fields, skip_locked=True)
        if changed == 0 and self._undo:
            document.segments = self._undo.pop()
        return changed

    def _require(self) -> SubtitleDocument:
        if self.document is None:
            raise SubtitleError("没有打开的字幕")
        return self.document

    def _push(self) -> None:
        document = self._require()
        self._undo.append(clone_segments(document.segments))
        self._trim()
        self._redo.clear()

    def _trim(self) -> None:
        extra = len(self._undo) - MAX_HISTORY
        if extra > 0:
            del self._undo[:extra]


def _same_times_and_text(left: list[SubtitleSegment], right: list[SubtitleSegment]) -> bool:
    if len(left) != len(right):
        return False
    for first, second in zip(left, right):
        if (
            first.start_time != second.start_time
            or first.end_time != second.end_time
            or first.source_text != second.source_text
            or first.corrected_text != second.corrected_text
            or first.translated_text != second.translated_text
            or first.locked != second.locked
        ):
            return False
    return True
