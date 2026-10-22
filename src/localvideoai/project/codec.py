"""Serialize project sections. Reuses subtitle sidecar fields so locks survive."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from localvideoai.core.types import AudioTrackInfo, MediaAnalysis, SubtitleTrackInfo, VideoTrackInfo
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.sidecar import segment_from_json, segment_to_json
from localvideoai.translation.resources import ResourceEntry, TranslationResources


def document_to_dict(document: SubtitleDocument | None) -> dict[str, Any] | None:
    if document is None:
        return None
    return {
        "format_name": document.format_name or "srt",
        "encoding": document.encoding,
        "detected_language": document.detected_language,
        "container_language": document.container_language,
        "quality_stage": document.quality_stage,
        "source_path": str(document.source_path) if document.source_path else "",
        "warnings": list(document.warnings),
        "speaker_map": dict(document.speaker_map),
        "speaker_styles": dict(document.speaker_styles),
        "segments": [segment_to_json(item) for item in document.segments],
    }


def document_from_dict(payload: dict[str, Any] | None) -> SubtitleDocument | None:
    if not payload:
        return None
    source = str(payload.get("source_path") or "")
    return SubtitleDocument(
        segments=[
            segment_from_json(item, index)
            for index, item in enumerate(payload.get("segments") or [], start=1)
            if isinstance(item, dict)
        ],
        format_name=str(payload.get("format_name") or "srt"),
        encoding=str(payload.get("encoding") or "utf-8"),
        detected_language=str(payload.get("detected_language") or ""),
        container_language=str(payload.get("container_language") or ""),
        quality_stage=str(payload.get("quality_stage") or ""),
        source_path=Path(source) if source else None,
        warnings=list(payload.get("warnings") or []),
        speaker_map=dict(payload.get("speaker_map") or {}),
        speaker_styles=dict(payload.get("speaker_styles") or {}),
    )


def analysis_to_dict(analysis: MediaAnalysis | None) -> dict[str, Any]:
    if analysis is None:
        return {}
    video = analysis.primary_video
    return {
        "path": str(analysis.path),
        "size_bytes": analysis.size_bytes,
        "duration_ms": analysis.duration_ms,
        "format_name": analysis.format_name,
        "width": video.width if video else None,
        "height": video.height if video else None,
        "fps": video.fps if video else None,
        "video_tracks": [_video_track(item) for item in analysis.video_tracks],
        "audio_tracks": [_audio_track(item) for item in analysis.audio_tracks],
        "subtitle_tracks": [_subtitle_track(item) for item in analysis.subtitle_tracks],
        "has_embedded_subtitles": analysis.has_embedded_subtitles,
    }


def analysis_from_dict(payload: dict[str, Any] | None) -> MediaAnalysis | None:
    if not payload or not payload.get("path"):
        return None
    return MediaAnalysis(
        path=Path(str(payload["path"])),
        size_bytes=int(payload.get("size_bytes") or 0),
        duration_ms=int(payload.get("duration_ms") or 0),
        format_name=str(payload.get("format_name") or ""),
        video_tracks=[
            VideoTrackInfo(
                index=int(item.get("index") or 0),
                codec=str(item.get("codec") or ""),
                width=item.get("width"),
                height=item.get("height"),
                fps=item.get("fps"),
                bitrate_bps=item.get("bitrate_bps"),
                language=item.get("language"),
            )
            for item in payload.get("video_tracks") or []
            if isinstance(item, dict)
        ],
        audio_tracks=[
            AudioTrackInfo(
                index=int(item.get("index") or 0),
                codec=str(item.get("codec") or ""),
                sample_rate=item.get("sample_rate"),
                channels=item.get("channels"),
                language=item.get("language"),
                bitrate_bps=item.get("bitrate_bps"),
            )
            for item in payload.get("audio_tracks") or []
            if isinstance(item, dict)
        ],
        subtitle_tracks=[
            SubtitleTrackInfo(
                index=int(item.get("index") or 0),
                codec=str(item.get("codec") or ""),
                format_name=str(item.get("format_name") or ""),
                language=item.get("language"),
                title=item.get("title"),
                is_default=bool(item.get("is_default")),
            )
            for item in payload.get("subtitle_tracks") or []
            if isinstance(item, dict)
        ],
    )


class ProjectTranslationResources(TranslationResources):
    """Glossary / TM / names stored inside the .vtproj, not uploaded."""

    def __init__(self, terms: dict[str, list] | None = None) -> None:
        super().__init__()
        self._terms = terms or {}

    def load_user(self, kind):  # type: ignore[override]
        return entries_from_json(self._terms.get(kind) or [])


def entries_to_json(entries: list[ResourceEntry]) -> list[dict[str, str]]:
    return [item.to_json() for item in entries]


def entries_from_json(items: list[dict[str, Any]] | None) -> list[ResourceEntry]:
    result: list[ResourceEntry] = []
    for item in items or []:
        if not isinstance(item, dict) or not str(item.get("source") or "").strip():
            continue
        result.append(
            ResourceEntry(
                source=str(item.get("source") or ""),
                target=str(item.get("target") or ""),
                source_lang=str(item.get("source_lang") or ""),
                target_lang=str(item.get("target_lang") or ""),
                note=str(item.get("note") or ""),
                origin="project",
            )
        )
    return result


def lock_ids(document: SubtitleDocument | None) -> dict[str, list[int]]:
    if document is None:
        return {"locked_ids": [], "confirmed_ids": []}
    locked = [item.id for item in document.segments if item.locked]
    confirmed: list[int] = []
    for item in document.segments:
        extra = item.extra.get("qa") if isinstance(item.extra, dict) else {}
        if isinstance(extra, dict) and extra.get("confirmed"):
            confirmed.append(item.id)
    return {"locked_ids": locked, "confirmed_ids": confirmed}


def _video_track(item: VideoTrackInfo) -> dict[str, Any]:
    return {
        "index": item.index,
        "codec": item.codec,
        "width": item.width,
        "height": item.height,
        "fps": item.fps,
        "bitrate_bps": item.bitrate_bps,
        "language": item.language,
    }


def _audio_track(item: AudioTrackInfo) -> dict[str, Any]:
    return {
        "index": item.index,
        "codec": item.codec,
        "sample_rate": item.sample_rate,
        "channels": item.channels,
        "language": item.language,
        "bitrate_bps": item.bitrate_bps,
    }


def _subtitle_track(item: SubtitleTrackInfo) -> dict[str, Any]:
    return {
        "index": item.index,
        "codec": item.codec,
        "format_name": item.format_name,
        "language": item.language,
        "title": item.title,
        "is_default": item.is_default,
    }
