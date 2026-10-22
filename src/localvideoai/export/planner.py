"""Decide remux vs re-encode. Subtitle-only changes must not re-encode the picture."""

from __future__ import annotations

from dataclasses import dataclass

from localvideoai.core.exceptions import ExportError
from localvideoai.core.types import ExportRequest, MediaAnalysis
from localvideoai.export.types import EXPORT_CONTAINERS, EXPORT_MODES


@dataclass(frozen=True)
class ExportPlan:
    mode: str
    container: str
    encode_mode: str
    video_codec: str
    audio_codec: str
    subtitle_codec: str
    reason: str


def source_video_codec(analysis: MediaAnalysis) -> str:
    track = analysis.primary_video
    return (track.codec if track else "").lower()


def source_audio_codec(analysis: MediaAnalysis) -> str:
    if not analysis.audio_tracks:
        return ""
    return (analysis.audio_tracks[0].codec or "").lower()


def normalize_mode(request: ExportRequest) -> str:
    if request.burn_in or request.picture_changed:
        return "burn_in"
    mode = (request.mode or "sidecar").strip().lower()
    if mode not in EXPORT_MODES:
        raise ExportError(f"未知导出模式：{request.mode}")
    return mode


def normalize_container(request: ExportRequest, output_suffix: str) -> str:
    raw = (request.container or output_suffix or "mp4").strip().lower().lstrip(".")
    if raw == "mov":
        return "mp4"
    if raw not in EXPORT_CONTAINERS:
        raise ExportError(f"不支持的容器：{raw}")
    return raw


def plan_export(request: ExportRequest, analysis: MediaAnalysis) -> ExportPlan:
    mode = normalize_mode(request)
    container = normalize_container(request, request.output_path.suffix)
    src_video = source_video_codec(analysis)
    wanted = (request.video_codec or "copy").strip().lower()
    picture_changed = bool(request.picture_changed or request.burn_in or mode == "burn_in")
    if picture_changed:
        codec = "h265" if wanted == "h265" else "h264"
        if container == "webm":
            codec = "vp9"
        return ExportPlan(
            mode=mode,
            container=container,
            encode_mode="encode",
            video_codec=codec,
            audio_codec=_audio_for_container(container),
            subtitle_codec="",
            reason="画面改变（烧录字幕），必须重新编码",
        )
    if container == "webm" and src_video not in {"vp8", "vp9", "av1"}:
        return ExportPlan(
            mode=mode,
            container=container,
            encode_mode="encode",
            video_codec="vp9",
            audio_codec="libopus",
            subtitle_codec="webvtt" if mode in {"embed", "multilingual", "project"} else "",
            reason="WebM 不能无损封装当前视频编码，只能重编码为 VP9",
        )
    if wanted == "h265" and src_video not in {"hevc", "h265"}:
        return ExportPlan(
            mode=mode,
            container=container,
            encode_mode="encode",
            video_codec="h265",
            audio_codec=_audio_for_container(container, copy_ok=True, source=source_audio_codec(analysis)),
            subtitle_codec=_sub_codec(container, mode),
            reason="目标是 H.265，源不是 HEVC，只能重新编码",
        )
    if wanted == "h264" and src_video not in {"h264", "avc"}:
        return ExportPlan(
            mode=mode,
            container=container,
            encode_mode="encode",
            video_codec="h264",
            audio_codec=_audio_for_container(container, copy_ok=True, source=source_audio_codec(analysis)),
            subtitle_codec=_sub_codec(container, mode),
            reason="目标是 H.264，源编码不同，只能重新编码",
        )
    return ExportPlan(
        mode=mode,
        container=container,
        encode_mode="remux",
        video_codec="copy",
        audio_codec="copy" if analysis.audio_tracks else "",
        subtitle_codec=_sub_codec(container, mode),
        reason="只改字幕轨道或容器，优先 remux，不重编码画面",
    )


def _audio_for_container(container: str, copy_ok: bool = False, source: str = "") -> str:
    if container == "webm":
        return "libopus"
    if copy_ok and source in {"aac", "mp3", "ac3"}:
        return "copy"
    return "aac"


def _sub_codec(container: str, mode: str) -> str:
    if mode not in {"embed", "multilingual", "project"}:
        return ""
    if container == "mkv":
        return "srt"
    if container == "webm":
        return "webvtt"
    return "mov_text"
