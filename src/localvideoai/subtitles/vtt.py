from __future__ import annotations

import re

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.timecodes import format_vtt_timestamp, parse_timestamp
_CUE_TIME = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})(?P<settings>.*)$"
)
_VOICE = re.compile(r"^<v(?:\s+([^>]+))?>(.*)$", re.DOTALL)


def parse_vtt(text: str) -> tuple[list[SubtitleSegment], list[str]]:
    warnings: list[str] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    body = normalized
    if body.lstrip().upper().startswith("WEBVTT"):
        first_newline = body.find("\n")
        body = body[first_newline + 1 :] if first_newline >= 0 else ""
    segments: list[SubtitleSegment] = []
    next_id = 1
    blocks = re.split(r"\n\s*\n", body.strip())
    for raw in blocks:
        lines = [line for line in raw.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines:
            continue
        head = lines[0].strip()
        if head.upper().startswith(("NOTE", "STYLE", "REGION", "WEBVTT")):
            continue
        time_index = 0
        identifier = ""
        if not _CUE_TIME.match(head) and len(lines) > 1:
            identifier = head
            time_index = 1
        if time_index >= len(lines):
            warnings.append(f"跳过缺少时间轴的 VTT 块：{head[:40]}")
            continue
        match = _CUE_TIME.match(lines[time_index].strip())
        if not match:
            warnings.append(f"跳过无法解析的 VTT 块：{lines[time_index][:80]}")
            continue
        try:
            start = parse_timestamp(match.group("start"))
            end = parse_timestamp(match.group("end"))
        except SubtitleError as exc:
            warnings.append(str(exc))
            continue
        if end < start:
            warnings.append(f"跳过结束时间早于开始时间的 VTT 字幕：{lines[time_index].strip()}")
            continue
        payload = "\n".join(lines[time_index + 1 :]).strip("\n")
        speaker = ""
        voice = _VOICE.match(payload)
        if voice:
            speaker = (voice.group(1) or "").strip()
            payload = (voice.group(2) or "").strip()
        payload = re.sub(r"</v>\s*$", "", payload).strip()
        extra = {}
        settings = (match.group("settings") or "").strip()
        if settings:
            extra["vtt_settings"] = settings
        if identifier:
            extra["vtt_id"] = identifier
        segments.append(
            SubtitleSegment(
                id=next_id,
                start_time=start,
                end_time=end,
                speaker=speaker,
                source_text=payload,
                extra=extra,
            )
        )
        next_id += 1
    return segments, warnings


def render_vtt(document: SubtitleDocument) -> str:
    lines = ["WEBVTT", ""]
    for segment in document.segments:
        cue_id = str(segment.extra.get("vtt_id") or segment.id)
        lines.append(cue_id)
        settings = segment.extra.get("vtt_settings")
        stamp = f"{format_vtt_timestamp(segment.start_time)} --> {format_vtt_timestamp(segment.end_time)}"
        if settings:
            stamp = f"{stamp} {settings}"
        lines.append(stamp)
        text = segment.display_text().replace("\r\n", "\n").replace("\r", "\n")
        if segment.speaker:
            text = f"<v {segment.speaker}>{text}"
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
