from __future__ import annotations

import re

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.timecodes import format_srt_timestamp, parse_timestamp

_TIME_LINE = re.compile(
    r"^\s*(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)


def parse_srt(text: str) -> tuple[list[SubtitleSegment], list[str]]:
    warnings: list[str] = []
    segments: list[SubtitleSegment] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    next_id = 1
    for raw in blocks:
        lines = [line for line in raw.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue
        time_index = 0
        if re.fullmatch(r"\d+", lines[0].strip()) and len(lines) > 1:
            time_index = 1
        if time_index >= len(lines):
            warnings.append(f"跳过缺少时间轴的字幕块：{lines[0][:40]}")
            continue
        match = _TIME_LINE.match(lines[time_index].strip())
        if not match:
            warnings.append(f"跳过无法解析的字幕块：{lines[time_index][:80]}")
            continue
        try:
            start = parse_timestamp(match.group("start"))
            end = parse_timestamp(match.group("end"))
        except SubtitleError as exc:
            warnings.append(str(exc))
            continue
        if end < start:
            warnings.append(f"跳过结束时间早于开始时间的字幕：{lines[time_index].strip()}")
            continue
        body = "\n".join(line.strip("\ufeff") for line in lines[time_index + 1 :]).strip("\n")
        segments.append(
            SubtitleSegment(
                id=next_id,
                start_time=start,
                end_time=end,
                source_text=body,
            )
        )
        next_id += 1
    return segments, warnings


def render_srt(document: SubtitleDocument) -> str:
    lines: list[str] = []
    for index, segment in enumerate(document.segments, start=1):
        lines.append(str(index))
        lines.append(f"{format_srt_timestamp(segment.start_time)} --> {format_srt_timestamp(segment.end_time)}")
        text = segment.display_text().replace("\r\n", "\n").replace("\r", "\n")
        lines.append(text if text else "")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
