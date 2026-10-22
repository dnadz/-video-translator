from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import MediaError
from localvideoai.core.types import AudioTrackInfo, MediaAnalysis, SubtitleTrackInfo, VideoTrackInfo
from localvideoai.media.ffmpeg_runtime import find_ffmpeg, find_ffprobe

_STREAM_RE = re.compile(
    r"^\s*Stream #(\d+):(\d+)(?:\[.*?\])?(?:\(([^)]*)\))?:\s*"
    r"(Video|Audio|Subtitle|Data|Attachment):\s*(.+)$"
)
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_INPUT_RE = re.compile(r"^Input #\d+,\s*(.+?),\s*from")
_SIZE_RE = re.compile(r"(\d{2,5})x(\d{2,5})")
_FPS_RE = re.compile(r"([\d.]+)\s*fps")
_TBR_RE = re.compile(r"([\d.]+)\s*tbr")
_HZ_RE = re.compile(r"(\d+)\s*Hz")
_CHANNELS_COUNT_RE = re.compile(r"(\d+)\s*channels?", re.IGNORECASE)
_BITRATE_RE = re.compile(r"(\d+)\s*kb/s")
_METADATA_RE = re.compile(r"^\s{2,}([A-Za-z0-9_]+)\s*:\s*(.*)$")

_CHANNEL_LAYOUTS = {
    "mono": 1,
    "stereo": 2,
    "2.1": 3,
    "3.0": 3,
    "4.0": 4,
    "quad": 4,
    "5.0": 5,
    "5.1": 6,
    "6.1": 7,
    "7.1": 8,
}

_SUBTITLE_FORMATS = {
    "subrip": "SRT",
    "srt": "SRT",
    "ass": "ASS",
    "ssa": "SSA",
    "webvtt": "VTT",
    "mov_text": "MOV_TEXT",
    "text": "TEXT",
    "hdmv_pgs_subtitle": "PGS",
    "dvd_subtitle": "VOBSUB",
    "dvdsub": "VOBSUB",
    "dvb_subtitle": "DVB",
    "dvb_teletext": "TELETEXT",
    "eia_608": "CEA-608",
    "closed_caption": "CC",
    "timed_id3": "ID3",
}


def subtitle_format_name(codec: str) -> str:
    key = (codec or "").strip().lower()
    if key in _SUBTITLE_FORMATS:
        return _SUBTITLE_FORMATS[key]
    return (codec or "unknown").upper()


def parse_frame_rate(value: object) -> float | None:
    if value in (None, "", "0/0", "N/A"):
        return None
    text = str(value).strip()
    if "/" in text:
        left, right = text.split("/", 1)
        try:
            denom = float(right)
            if denom == 0:
                return None
            result = float(left) / denom
        except ValueError:
            return None
        return result if math.isfinite(result) and result > 0 else None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) and result > 0 else None


def dump_ffmpeg_info(source: Path) -> str:
    ffmpeg = find_ffmpeg()
    completed = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-i", str(source)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return (completed.stderr or "") + "\n" + (completed.stdout or "")


def analyze_with_ffprobe(source: Path) -> MediaAnalysis:
    probe = find_ffprobe()
    command = [
        str(probe),
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-show_entries",
        "stream_tags=language,title,handler_name:format_tags=encoder",
        "-print_format",
        "json",
        str(source),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise MediaError(f"无法读取视频：{source}\n{(completed.stderr or '')[-2000:]}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"无法解析媒体信息：{source}") from exc
    if not isinstance(payload, dict):
        raise MediaError(f"无法解析媒体信息：{source}")
    fmt = payload.get("format") or {}
    duration_ms = _duration_seconds_to_ms(fmt.get("duration"))
    size_bytes = int(fmt.get("size") or source.stat().st_size)
    format_name = str(fmt.get("format_name") or source.suffix.lstrip(".") or "unknown")
    video_tracks: list[VideoTrackInfo] = []
    audio_tracks: list[AudioTrackInfo] = []
    subtitle_tracks: list[SubtitleTrackInfo] = []
    for raw in payload.get("streams") or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("codec_type") or "unknown").lower()
        if kind == "video":
            video_tracks.append(_video_from_ffprobe(raw))
        elif kind == "audio":
            audio_tracks.append(_audio_from_ffprobe(raw))
        elif kind == "subtitle":
            subtitle_tracks.append(_subtitle_from_ffprobe(raw))
    if not video_tracks and not audio_tracks and not subtitle_tracks:
        raise MediaError(f"无法读取视频：文件中没有可识别的媒体轨道：{source}")
    return MediaAnalysis(
        path=source,
        size_bytes=size_bytes,
        duration_ms=duration_ms,
        format_name=format_name,
        video_tracks=video_tracks,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
    )


def analyze_with_ffmpeg(source: Path) -> MediaAnalysis:
    text = dump_ffmpeg_info(source)
    if _looks_unreadable(text):
        raise MediaError(f"无法读取视频：{source}\n{_error_excerpt(text)}")
    return parse_ffmpeg_info(source, text)


def parse_ffmpeg_info(source: Path, text: str) -> MediaAnalysis:
    format_name = source.suffix.lstrip(".") or "unknown"
    duration_ms = 0
    video_tracks: list[VideoTrackInfo] = []
    audio_tracks: list[AudioTrackInfo] = []
    subtitle_tracks: list[SubtitleTrackInfo] = []
    pending: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal pending
        if pending is None:
            return
        kind = pending.pop("kind")
        if kind == "video":
            video_tracks.append(_video_from_parsed(pending))
        elif kind == "audio":
            audio_tracks.append(_audio_from_parsed(pending))
        elif kind == "subtitle":
            subtitle_tracks.append(_subtitle_from_parsed(pending))
        pending = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        input_match = _INPUT_RE.match(line)
        if input_match:
            format_name = input_match.group(1).strip()
            continue
        duration_match = _DURATION_RE.search(line)
        if duration_match and duration_ms == 0:
            hours, minutes, seconds = duration_match.groups()
            duration_ms = int(((int(hours) * 60 + int(minutes)) * 60 + float(seconds)) * 1000)
            continue
        stream_match = _STREAM_RE.match(line)
        if stream_match:
            flush()
            _stream_id, index_text, language, kind, rest = stream_match.groups()
            pending = {
                "kind": kind.lower(),
                "index": int(index_text),
                "language": _normalize_language(language),
                "rest": rest.strip(),
                "title": None,
                "is_default": "default" in rest.lower(),
            }
            continue
        if pending is None:
            continue
        if line.strip() == "Metadata:":
            continue
        meta = _METADATA_RE.match(line)
        if meta and not line.lstrip().startswith("Stream #"):
            key, value = meta.group(1).lower(), meta.group(2).strip()
            if key == "language" and value:
                pending["language"] = _normalize_language(value) or pending.get("language")
            elif key == "title" and value:
                pending["title"] = value
            elif key == "handler_name" and value and not pending.get("title"):
                pending["handler_name"] = value
    flush()
    if not video_tracks and not audio_tracks and not subtitle_tracks:
        raise MediaError(f"无法读取视频：FFmpeg 没有列出媒体轨道：{source}\n{_error_excerpt(text)}")
    return MediaAnalysis(
        path=source,
        size_bytes=source.stat().st_size,
        duration_ms=duration_ms,
        format_name=format_name,
        video_tracks=video_tracks,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
    )


def _looks_unreadable(text: str) -> bool:
    lowered = text.lower()
    if "stream #" in lowered or "duration:" in lowered:
        return False
    markers = (
        "invalid data found",
        "error opening input",
        "no such file",
        "permission denied",
        "immediate exit requested",
        "could not find codec",
        "moov atom not found",
        "invalid argument",
        "unknown format",
    )
    return any(marker in lowered for marker in markers) or ("input #" not in lowered)


def _error_excerpt(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    useful = [
        line
        for line in lines
        if not line.lower().startswith("ffmpeg version") and "configuration:" not in line.lower()
    ]
    excerpt = "\n".join(useful[-12:] if useful else lines[-12:])
    return excerpt[:2000]


def _normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return text


def _codec_from_rest(rest: str) -> str:
    token = rest.split(",", 1)[0].split("(", 1)[0].strip()
    token = token.split(" ", 1)[0].strip()
    return token or "unknown"


def _video_from_parsed(pending: dict[str, Any]) -> VideoTrackInfo:
    rest = str(pending.get("rest") or "")
    size = _SIZE_RE.search(rest)
    fps = None
    fps_match = _FPS_RE.search(rest)
    tbr_match = _TBR_RE.search(rest)
    if fps_match:
        fps = parse_frame_rate(fps_match.group(1))
    elif tbr_match:
        fps = parse_frame_rate(tbr_match.group(1))
    bitrate = None
    bitrate_match = _BITRATE_RE.search(rest)
    if bitrate_match:
        bitrate = int(bitrate_match.group(1)) * 1000
    return VideoTrackInfo(
        index=int(pending["index"]),
        codec=_codec_from_rest(rest),
        width=int(size.group(1)) if size else None,
        height=int(size.group(2)) if size else None,
        fps=fps,
        bitrate_bps=bitrate,
        language=pending.get("language"),
        extra={"raw": rest},
    )


def _audio_from_parsed(pending: dict[str, Any]) -> AudioTrackInfo:
    rest = str(pending.get("rest") or "")
    hz = _HZ_RE.search(rest)
    layout = None
    channels = None
    count = _CHANNELS_COUNT_RE.search(rest)
    if count:
        channels = int(count.group(1))
    else:
        for name, value in _CHANNEL_LAYOUTS.items():
            if re.search(rf"(^|,\s*){re.escape(name)}(\s*,|$)", rest, re.IGNORECASE):
                layout = name
                channels = value
                break
    bitrate = None
    bitrate_match = _BITRATE_RE.search(rest)
    if bitrate_match:
        bitrate = int(bitrate_match.group(1)) * 1000
    return AudioTrackInfo(
        index=int(pending["index"]),
        codec=_codec_from_rest(rest),
        sample_rate=int(hz.group(1)) if hz else None,
        channels=channels,
        channel_layout=layout,
        language=pending.get("language"),
        bitrate_bps=bitrate,
        extra={"raw": rest},
    )


def _subtitle_from_parsed(pending: dict[str, Any]) -> SubtitleTrackInfo:
    rest = str(pending.get("rest") or "")
    codec = _codec_from_rest(rest)
    return SubtitleTrackInfo(
        index=int(pending["index"]),
        codec=codec,
        format_name=subtitle_format_name(codec),
        language=pending.get("language"),
        title=pending.get("title"),
        is_default=bool(pending.get("is_default")),
        extra={"raw": rest},
    )


def _tags(raw: dict[str, Any]) -> dict[str, Any]:
    tags = raw.get("tags") or {}
    return tags if isinstance(tags, dict) else {}


def _video_from_ffprobe(raw: dict[str, Any]) -> VideoTrackInfo:
    tags = _tags(raw)
    fps = parse_frame_rate(raw.get("avg_frame_rate")) or parse_frame_rate(raw.get("r_frame_rate"))
    bitrate = raw.get("bit_rate")
    return VideoTrackInfo(
        index=int(raw.get("index") or 0),
        codec=str(raw.get("codec_name") or "unknown"),
        width=int(raw["width"]) if raw.get("width") else None,
        height=int(raw["height"]) if raw.get("height") else None,
        fps=fps,
        bitrate_bps=int(bitrate) if bitrate not in (None, "") else None,
        language=_normalize_language(str(tags["language"])) if tags.get("language") else None,
        extra={"profile": raw.get("codec_profile") or raw.get("profile")},
    )


def _audio_from_ffprobe(raw: dict[str, Any]) -> AudioTrackInfo:
    tags = _tags(raw)
    sample_rate = raw.get("sample_rate")
    channels = raw.get("channels")
    bitrate = raw.get("bit_rate")
    layout = raw.get("channel_layout")
    return AudioTrackInfo(
        index=int(raw.get("index") or 0),
        codec=str(raw.get("codec_name") or "unknown"),
        sample_rate=int(sample_rate) if sample_rate not in (None, "") else None,
        channels=int(channels) if channels not in (None, "") else None,
        channel_layout=str(layout) if layout else None,
        language=_normalize_language(str(tags["language"])) if tags.get("language") else None,
        bitrate_bps=int(bitrate) if bitrate not in (None, "") else None,
        extra={},
    )


def _subtitle_from_ffprobe(raw: dict[str, Any]) -> SubtitleTrackInfo:
    tags = _tags(raw)
    codec = str(raw.get("codec_name") or "unknown")
    disposition = raw.get("disposition") or {}
    is_default = bool(disposition.get("default")) if isinstance(disposition, dict) else False
    return SubtitleTrackInfo(
        index=int(raw.get("index") or 0),
        codec=codec,
        format_name=subtitle_format_name(codec),
        language=_normalize_language(str(tags["language"])) if tags.get("language") else None,
        title=str(tags["title"]) if tags.get("title") else None,
        is_default=is_default,
        extra={},
    )


def _duration_seconds_to_ms(value: object) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value)) * 1000)
    except ValueError as exc:
        raise MediaError(f"无法解析时长：{value}") from exc
