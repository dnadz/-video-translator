"""Extract text subtitle streams from a video with bundled FFmpeg."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from localvideoai.core.exceptions import MediaError, SubtitleError
from localvideoai.core.types import EmbeddedSubtitleTrack, SubtitleTrackInfo
from localvideoai.media.ffmpeg_runtime import find_ffmpeg
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import load_subtitle, save_subtitle
from localvideoai.subtitles.language import detect_script_language, identify_language, normalize_language_tag

BITMAP_CODECS = frozenset(
    {
        "hdmv_pgs_subtitle",
        "pgssub",
        "pgs",
        "dvd_subtitle",
        "dvdsub",
        "dvb_subtitle",
        "dvbsub",
        "xsub",
        "dvb_teletext",
    }
)

COPY_EXTENSIONS = {
    "subrip": ".srt",
    "srt": ".srt",
    "ass": ".ass",
    "ssa": ".ssa",
    "webvtt": ".vtt",
}


def is_bitmap_subtitle(codec: str, format_name: str = "") -> bool:
    keys = {(codec or "").strip().lower(), (format_name or "").strip().lower()}
    if keys & BITMAP_CODECS:
        return True
    if "PGS" in (format_name or "").upper() or "VOBSUB" in (format_name or "").upper():
        return True
    if (format_name or "").upper() in {"DVB", "TELETEXT"}:
        return True
    return False


def unreadable_reason(codec: str, format_name: str = "") -> str:
    if is_bitmap_subtitle(codec, format_name):
        return "字幕轨道不可读取：图像字幕（PGS / VOBSUB / DVB）无法提取为文本，需要后续 OCR 阶段。"
    return ""


def describe_track(track: SubtitleTrackInfo, ordinal: int) -> EmbeddedSubtitleTrack:
    container = track.language or ""
    normalized = normalize_language_tag(container) or "und"
    reason = unreadable_reason(track.codec, track.format_name)
    return EmbeddedSubtitleTrack(
        index=track.index,
        ordinal=ordinal,
        codec=track.codec,
        format_name=track.format_name,
        language=normalized,
        container_language=container,
        title=track.title or "",
        is_default=track.is_default,
        readable=not bool(reason),
        unreadable_reason=reason,
    )


def list_embedded_tracks(video_path: Path, analyzer: MediaAnalyzer | None = None) -> list[EmbeddedSubtitleTrack]:
    source = video_path.expanduser().resolve()
    try:
        analysis = (analyzer or MediaAnalyzer()).analyze(source)
    except MediaError as exc:
        raise SubtitleError(str(exc)) from exc
    return [describe_track(track, ordinal) for ordinal, track in enumerate(analysis.subtitle_tracks)]


def extract_embedded_track(
    video_path: Path,
    stream_index: int,
    destination: Path | None = None,
    analyzer: MediaAnalyzer | None = None,
    timeout_sec: int = 120,
) -> SubtitleDocument:
    source = video_path.expanduser().resolve()
    tracks = list_embedded_tracks(source, analyzer=analyzer)
    if not tracks:
        raise SubtitleError(f"字幕轨道不可读取：视频没有内嵌字幕轨道：{source}")
    track = next((item for item in tracks if item.index == stream_index), None)
    if track is None:
        raise SubtitleError(f"字幕轨道不可读取：找不到编号 {stream_index} 的字幕轨道：{source}")
    if not track.readable:
        raise SubtitleError(track.unreadable_reason)
    dumped = _dump_stream(source, track, timeout_sec=timeout_sec)
    try:
        document = load_subtitle(dumped)
    except SubtitleError as exc:
        raise SubtitleError(f"字幕轨道不可读取：{exc}") from exc
    if not document.segments:
        raise SubtitleError(f"字幕轨道不可读取：轨道 #{track.index} 没有有效字幕条目")
    _apply_language(document, track.container_language)
    document.embedded_stream_index = track.index
    if destination is not None:
        fmt = destination.suffix.lstrip(".").lower() or document.format_name
        save_subtitle(document, destination, fmt)
    return document


def preview_embedded_track(
    video_path: Path,
    stream_index: int,
    max_cues: int = 40,
    analyzer: MediaAnalyzer | None = None,
) -> SubtitleDocument:
    document = extract_embedded_track(video_path, stream_index, analyzer=analyzer)
    if len(document.segments) <= max_cues:
        return document
    preview = SubtitleDocument(
        segments=list(document.segments[:max_cues]),
        format_name=document.format_name,
        source_path=document.source_path,
        encoding=document.encoding,
        warnings=list(document.warnings)
        + [f"预览仅显示前 {max_cues} 条，共 {len(document.segments)} 条。"],
        script_info=list(document.script_info),
        style_section=document.style_section,
        events_format=document.events_format,
        embedded_stream_index=document.embedded_stream_index,
        container_language=document.container_language,
        detected_language=document.detected_language,
    )
    return preview


def _apply_language(document: SubtitleDocument, container_language: str) -> None:
    text = "\n".join(item.source_text for item in document.segments)
    script = detect_script_language(text)
    chosen = identify_language(text, container_language)
    document.container_language = container_language or ""
    document.detected_language = script or chosen
    for segment in document.segments:
        if not segment.language.strip():
            segment.language = chosen


def _dump_stream(source: Path, track: EmbeddedSubtitleTrack, timeout_sec: int) -> Path:
    ffmpeg = find_ffmpeg()
    suffix = COPY_EXTENSIONS.get(track.codec.lower()) or COPY_EXTENSIONS.get(track.format_name.lower()) or ".srt"
    work = Path(tempfile.mkdtemp(prefix="localvideoai-sub-"))
    native = work / f"track_{track.index}{suffix}"
    converted = work / f"track_{track.index}.srt"
    last_error = ""
    attempts = (
        (f"0:{track.index}", True, native),
        (f"0:s:{track.ordinal}", True, native),
        (f"0:{track.index}", False, converted),
        (f"0:s:{track.ordinal}", False, converted),
    )
    for map_spec, copy, dest in attempts:
        ok, detail = _run_ffmpeg_extract(ffmpeg, source, map_spec, dest, copy=copy, timeout_sec=timeout_sec)
        if ok:
            return dest
        last_error = detail
    raise SubtitleError(f"字幕轨道不可读取：提取失败（轨道 #{track.index}）\n{last_error[-1500:]}")


def _run_ffmpeg_extract(
    ffmpeg: Path,
    source: Path,
    map_spec: str,
    destination: Path,
    *,
    copy: bool,
    timeout_sec: int,
) -> tuple[bool, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        map_spec,
        "-vn",
        "-an",
        "-dn",
        "-map_metadata",
        "-1",
    ]
    if copy:
        command.extend(["-c:s", "copy"])
    else:
        command.extend(["-c:s", "srt"])
    command.append(str(destination))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"提取超时（{timeout_sec}s）：{exc}"
    log = (completed.stderr or "") + "\n" + (completed.stdout or "")
    if completed.returncode != 0:
        return False, log
    if not destination.is_file() or destination.stat().st_size <= 0:
        return False, log or "提取结果为空"
    return True, log
