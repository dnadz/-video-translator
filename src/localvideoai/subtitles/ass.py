from __future__ import annotations

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.timecodes import format_ass_timestamp, parse_timestamp

_DEFAULT_EVENTS = "Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"

_ASS_HEADER = """[Script Info]
; Converted by LocalVideoAI
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_SSA_HEADER = """[Script Info]
; Converted by LocalVideoAI
ScriptType: v4.00
PlayResX: 1920
PlayResY: 1080

[V4 Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, TertiaryColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, AlphaLevel, Encoding
Style: Default,Arial,48,16777215,255,0,0,0,0,1,2,2,2,10,10,10,0,1

[Events]
Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def parse_ass(text: str) -> tuple[list[SubtitleSegment], list[str], dict[str, object]]:
    warnings: list[str] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    script_info: list[str] = []
    style_lines: list[str] = []
    events_format = _DEFAULT_EVENTS
    in_info = in_styles = in_events = False
    segments: list[SubtitleSegment] = []
    next_id = 1
    for raw_line in normalized.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        header = stripped.lower()
        if header.startswith("[") and header.endswith("]"):
            in_info = header == "[script info]"
            in_styles = header in {"[v4+ styles]", "[v4 styles]"}
            in_events = header == "[events]"
            if in_styles:
                style_lines.append(line)
            continue
        if in_info:
            if stripped and not stripped.startswith(";"):
                script_info.append(line)
            continue
        if in_styles:
            style_lines.append(line)
            continue
        if not in_events:
            continue
        if stripped.lower().startswith("format:"):
            events_format = stripped.split(":", 1)[1].strip()
            continue
        kind, _, payload = stripped.partition(":")
        if kind.strip().lower() != "dialogue" or not payload:
            continue
        try:
            fields = _split_event(payload.lstrip(), events_format)
        except SubtitleError as exc:
            warnings.append(str(exc))
            continue
        start_raw = fields.get("start", "")
        end_raw = fields.get("end", "")
        try:
            start = parse_timestamp(start_raw, centiseconds=True)
            end = parse_timestamp(end_raw, centiseconds=True)
        except SubtitleError as exc:
            warnings.append(str(exc))
            continue
        if end < start:
            warnings.append(f"跳过结束时间早于开始时间的 ASS 字幕：{start_raw} --> {end_raw}")
            continue
        text_body = _unescape_ass(fields.get("text", ""))
        segments.append(
            SubtitleSegment(
                id=next_id,
                start_time=start,
                end_time=end,
                speaker=fields.get("name", ""),
                source_text=text_body,
                style_id=fields.get("style", "") or "Default",
                extra={
                    "layer": fields.get("layer") or fields.get("marked") or "0",
                    "margin_l": fields.get("marginl", "0"),
                    "margin_r": fields.get("marginr", "0"),
                    "margin_v": fields.get("marginv", "0"),
                    "effect": fields.get("effect", ""),
                },
            )
        )
        next_id += 1
    meta: dict[str, object] = {
        "script_info": script_info,
        "style_section": "\n".join(style_lines).strip(),
        "events_format": events_format,
    }
    return segments, warnings, meta


def render_ass(document: SubtitleDocument, fmt: str) -> str:
    fmt = fmt.lower()
    ssa = fmt == "ssa"
    default_format = (
        "Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text" if ssa else _DEFAULT_EVENTS
    )
    event_format = document.events_format or default_format
    if document.script_info or document.style_section:
        chunks = ["[Script Info]"]
        if document.script_info:
            chunks.extend(document.script_info)
        else:
            chunks.append("ScriptType: v4.00" if ssa else "ScriptType: v4.00+")
        chunks.append("")
        style = document.style_section.strip()
        if style:
            if not style.lstrip().startswith("["):
                chunks.append("[V4 Styles]" if ssa else "[V4+ Styles]")
            chunks.append(style)
            chunks.append("")
        chunks.append("[Events]")
        chunks.append(f"Format: {event_format}")
        header = "\n".join(chunks).rstrip()
    else:
        header = (_SSA_HEADER if ssa else _ASS_HEADER).rstrip()
        event_format = default_format
    keys = [item.strip().lower() for item in event_format.split(",") if item.strip()]
    lines = [header, ""]
    for segment in document.segments:
        extra = segment.extra
        values = {
            "layer": extra.get("layer", "0"),
            "marked": extra.get("layer", "0"),
            "start": format_ass_timestamp(segment.start_time),
            "end": format_ass_timestamp(segment.end_time),
            "style": segment.style_id or "Default",
            "name": segment.speaker,
            "marginl": extra.get("margin_l", "0"),
            "marginr": extra.get("margin_r", "0"),
            "marginv": extra.get("margin_v", "0"),
            "effect": extra.get("effect", ""),
            "text": _escape_ass(segment.display_text()),
        }
        rendered = ",".join(str(values.get(key, "")) for key in keys)
        lines.append(f"Dialogue: {rendered}")
    return "\n".join(lines).rstrip() + "\n"


def _split_event(payload: str, events_format: str) -> dict[str, str]:
    keys = [item.strip().lower() for item in events_format.split(",") if item.strip()]
    if not keys:
        raise SubtitleError("ASS Events Format 无效")
    text_index = keys.index("text") if "text" in keys else len(keys) - 1
    parts = payload.split(",", text_index)
    if len(parts) < text_index:
        raise SubtitleError(f"ASS Dialogue 字段不足：{payload[:80]}")
    values = parts[:text_index] + [",".join(parts[text_index:])]
    while len(values) < len(keys):
        values.append("")
    return {key: values[index].strip() if key != "text" else values[index] for index, key in enumerate(keys)}


def _unescape_ass(text: str) -> str:
    return text.replace("\\N", "\n").replace("\\n", "\n")


def _escape_ass(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\N")
