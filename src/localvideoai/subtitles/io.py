from __future__ import annotations

from pathlib import Path

from localvideoai.core.exceptions import SubtitleError
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.ass import parse_ass, render_ass
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.encoding import read_subtitle_text, write_subtitle_text
from localvideoai.subtitles.sidecar import apply_sidecar, write_sidecar
from localvideoai.subtitles.srt import parse_srt, render_srt
from localvideoai.subtitles.vtt import parse_vtt, render_vtt

SUPPORTED_FORMATS = ("srt", "ass", "ssa", "vtt")


def detect_format(path: Path, text: str) -> str:
    suffix = path.suffix.lower().lstrip(".")
    head = text.lstrip("\ufeff").lstrip()
    upper = head.upper()
    if upper.startswith("WEBVTT"):
        return "vtt"
    if "[SCRIPT INFO]" in upper:
        compact = upper.replace(" ", "")
        if "SCRIPTTYPE:V4.00+" in compact or suffix == "ass":
            return "ass" if suffix != "ssa" else "ssa"
        if suffix == "ssa" or "SCRIPTTYPE:V4.00" in compact:
            return "ssa"
        return "ass"
    if suffix in SUPPORTED_FORMATS:
        return suffix
    return "srt"


def load_subtitle(path: Path) -> SubtitleDocument:
    source = path.expanduser().resolve()
    if not source.exists():
        raise SubtitleError(f"字幕文件不存在：{source}")
    if not source.is_file():
        raise SubtitleError(f"不是字幕文件：{source}")
    text, encoding = read_subtitle_text(source)
    fmt = detect_format(source, text)
    script_info: list[str] = []
    style_section = ""
    events_format = ""
    if fmt == "vtt":
        segments, warnings = parse_vtt(text)
    elif fmt in {"ass", "ssa"}:
        segments, warnings, meta = parse_ass(text)
        script_info = list(meta.get("script_info") or [])
        style_section = str(meta.get("style_section") or "")
        events_format = str(meta.get("events_format") or "")
    else:
        segments, warnings = parse_srt(text)
    if not segments:
        warnings.append("没有解析到有效字幕条目。")
    document = SubtitleDocument(
        segments=segments,
        format_name=fmt,
        source_path=source,
        encoding=encoding,
        warnings=warnings,
        script_info=script_info,
        style_section=style_section,
        events_format=events_format,
    )
    ordered = document.sorted_copy()
    return apply_sidecar(ordered, source)


def save_subtitle(document: SubtitleDocument, path: Path, fmt: str | None = None) -> Path:
    destination = path.expanduser().resolve()
    chosen = (fmt or destination.suffix.lstrip(".") or document.format_name or "srt").lower()
    if chosen not in SUPPORTED_FORMATS:
        raise SubtitleError(f"不支持的字幕格式：{chosen}")
    ordered = document.sorted_copy()
    if chosen == "vtt":
        payload = render_vtt(ordered)
    elif chosen in {"ass", "ssa"}:
        payload = render_ass(ordered, chosen)
    else:
        payload = render_srt(ordered)
    write_subtitle_text(destination, payload)
    ordered.source_path = destination
    ordered.format_name = chosen
    ordered.encoding = "utf-8"
    write_sidecar(ordered, destination)
    document.segments = ordered.segments
    document.source_path = destination
    document.format_name = chosen
    document.encoding = "utf-8"
    return destination


def assign_ids(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    ordered = sorted(segments, key=lambda item: (item.start_time, item.end_time, item.id))
    for index, segment in enumerate(ordered, start=1):
        segment.id = index
    return ordered
