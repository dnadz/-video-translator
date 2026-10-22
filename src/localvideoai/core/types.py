"""Shared dataclasses for engine contracts. No runtime AI logic here."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MediaStreamInfo:
    index: int
    codec: str
    kind: str
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoTrackInfo:
    index: int
    codec: str
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    bitrate_bps: int | None = None
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioTrackInfo:
    index: int
    codec: str
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    language: str | None = None
    bitrate_bps: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubtitleTrackInfo:
    index: int
    codec: str
    format_name: str
    language: str | None = None
    title: str | None = None
    is_default: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddedSubtitleTrack:
    """Listed embedded subtitle stream, ready for extract / preview."""

    index: int
    ordinal: int
    codec: str
    format_name: str
    language: str
    container_language: str
    title: str
    is_default: bool = False
    readable: bool = True
    unreadable_reason: str = ""

    def label(self) -> str:
        title = f" {self.title}" if self.title else ""
        flag = "" if self.readable else "（不可读取）"
        lang = self.language or self.container_language or "und"
        return f"#{self.index} {lang} {self.format_name}{title}{flag}"


@dataclass(frozen=True)
class MediaAnalysis:
    path: Path
    size_bytes: int
    duration_ms: int
    format_name: str
    video_tracks: list[VideoTrackInfo] = field(default_factory=list)
    audio_tracks: list[AudioTrackInfo] = field(default_factory=list)
    subtitle_tracks: list[SubtitleTrackInfo] = field(default_factory=list)

    @property
    def has_embedded_subtitles(self) -> bool:
        return bool(self.subtitle_tracks)

    @property
    def primary_video(self) -> VideoTrackInfo | None:
        return self.video_tracks[0] if self.video_tracks else None

    def to_probe_result(self) -> "VideoProbeResult":
        streams: list[MediaStreamInfo] = []
        for track in self.video_tracks:
            streams.append(
                MediaStreamInfo(
                    index=track.index,
                    codec=track.codec,
                    kind="video",
                    language=track.language,
                    extra={"width": track.width, "height": track.height, "fps": track.fps},
                )
            )
        for track in self.audio_tracks:
            streams.append(
                MediaStreamInfo(
                    index=track.index,
                    codec=track.codec,
                    kind="audio",
                    language=track.language,
                    extra={"sample_rate": track.sample_rate, "channels": track.channels},
                )
            )
        for track in self.subtitle_tracks:
            streams.append(
                MediaStreamInfo(
                    index=track.index,
                    codec=track.codec,
                    kind="subtitle",
                    language=track.language,
                    extra={"format": track.format_name, "title": track.title},
                )
            )
        video = self.primary_video
        return VideoProbeResult(
            path=self.path,
            duration_ms=self.duration_ms,
            format_name=self.format_name,
            size_bytes=self.size_bytes,
            width=video.width if video else None,
            height=video.height if video else None,
            streams=streams,
        )


@dataclass(frozen=True)
class VideoProbeResult:
    path: Path
    duration_ms: int
    format_name: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    streams: list[MediaStreamInfo] = field(default_factory=list)


@dataclass
class SubtitleSegment:
    """Canonical subtitle unit for import, edit, save, and later translation."""

    id: int
    start_time: int
    end_time: int
    speaker: str = ""
    source_text: str = ""
    corrected_text: str = ""
    translated_text: str = ""
    language: str = ""
    confidence: float | None = None
    locked: bool = False
    style_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def display_text(self) -> str:
        corrected = self.corrected_text.strip()
        return corrected if corrected else self.source_text

    def to_cue(self) -> "SubtitleCue":
        return SubtitleCue(
            index=self.id,
            start_ms=self.start_time,
            end_ms=self.end_time,
            text=self.display_text(),
            speaker=self.speaker or None,
        )


@dataclass(frozen=True)
class SubtitleCue:
    index: int
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None


@dataclass(frozen=True)
class TranslationRequest:
    text: str
    source_lang: str
    target_lang: str
    context: str | None = None
    quality: str = "standard"
    device_preference: str = "auto"
    prefer_gpu: bool = True
    force_terms: tuple[tuple[str, str], ...] = ()
    session_memory: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TranslationResult:
    text: str
    source_lang: str
    target_lang: str
    model_id: str
    device: str = "cpu"
    quality: str = "standard"
    beam_size: int = 2
    via_memory: bool = False
    glossary_hits: int = 0
    character_hits: int = 0
    route: tuple[str, ...] = ()
    context_used: bool = False


@dataclass(frozen=True)
class SpeechWord:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class SpeechSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    speaker: str | None = None
    language: str = ""
    words: tuple[SpeechWord, ...] = ()


@dataclass
class DiarizationResult:
    turns: list[SpeechSegment]
    speaker_ids: tuple[str, ...] = ()
    model_id: str = ""
    device: str = "cpu"
    fallback: bool = False
    fallback_reason: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class SpeechTranscript:
    segments: list[SpeechSegment]
    language: str
    language_probability: float
    model_id: str
    device: str
    compute_type: str
    source_path: Path
    raw_path: Path | None = None
    duration_ms: int = 0
    chunk_count: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OCRBox:
    start_ms: int
    text: str
    confidence: float
    points: tuple[tuple[float, float], ...] = ()
    end_ms: int = 0


@dataclass(frozen=True)
class OCRCue:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    language: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0
    boxes: tuple[OCRBox, ...] = ()


@dataclass
class OCRTranscript:
    cues: list[OCRCue]
    language: str
    model_id: str
    device: str
    source_path: Path
    region: tuple[float, float, float, float]
    region_source: str
    duration_ms: int = 0
    frames_decoded: int = 0
    frames_ocr: int = 0
    raw_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    task_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ExportLanguageTrack:
    language: str
    title: str = ""
    subtitle_path: Path | None = None
    text_role: str = "display"


@dataclass(frozen=True)
class ExportRequest:
    video_path: Path
    subtitle_path: Path | None
    output_path: Path
    burn_in: bool = False
    mode: str = "sidecar"
    container: str = "mp4"
    video_codec: str = "copy"
    subtitle_format: str = "srt"
    tracks: tuple[ExportLanguageTrack, ...] = ()
    picture_changed: bool = False
    project_payload: dict[str, Any] | None = None
