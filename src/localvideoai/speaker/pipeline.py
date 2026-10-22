"""Local speaker diarization: VAD + embedding + clustering. No upload."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from localvideoai.audio.chunker import iter_pcm_chunks
from localvideoai.audio.window import extract_pcm_window
from localvideoai.core.types import DiarizationResult, SpeechSegment
from localvideoai.media.ffmpeg_runtime import find_ffmpeg
from localvideoai.speaker.assign import majority_speaker
from localvideoai.speaker.cluster import cluster_embeddings
from localvideoai.speaker.embed import SpeakerEmbedder
from localvideoai.speaker.features import pcm16_to_float
from localvideoai.speaker.labels import assign_canonical, ensure_speaker_styles, speaker_id
from localvideoai.speaker.store import is_speaker_model_ready, model_id
from localvideoai.speaker.vad import speech_windows
from localvideoai.subtitles.document import SubtitleDocument

ProgressCallback = Callable[[int, int, str], None]
FALLBACK_NO_MODEL = "未找到本机说话人模型，已保持普通字幕。"
FALLBACK_NO_SPEECH = "没有可用的语音片段，已保持普通字幕。"


def fallback_result(reason: str) -> DiarizationResult:
    return DiarizationResult(
        turns=[],
        speaker_ids=(),
        model_id="none",
        device="cpu",
        fallback=True,
        fallback_reason=reason,
    )


def diarize_media(
    audio_path: Path,
    *,
    embedder: SpeakerEmbedder | None = None,
    duration_ms: int | None = None,
    progress: ProgressCallback | None = None,
) -> DiarizationResult:
    if not is_speaker_model_ready():
        return fallback_result(FALLBACK_NO_MODEL)
    finder = embedder or SpeakerEmbedder()
    if not finder.available:
        return fallback_result(FALLBACK_NO_MODEL)
    find_ffmpeg()
    source = audio_path.expanduser().resolve()
    total = int(duration_ms or 0)
    if total <= 0:
        from localvideoai.media.media_analyzer import MediaAnalyzer

        total = max(MediaAnalyzer().analyze(source).duration_ms, 1)
    embeddings: list[np.ndarray] = []
    windows: list[tuple[int, int]] = []
    last_end = 0
    for chunk in iter_pcm_chunks(source, total):
        last_end = chunk.end_ms
        samples = pcm16_to_float(chunk.pcm_s16le)
        for start_ms, end_ms in speech_windows(samples, offset_ms=chunk.start_ms):
            piece = extract_pcm_window(source, start_ms, end_ms, accurate_seek=True)
            vector = finder.embed_pcm(piece.pcm_s16le)
            if vector is None:
                continue
            embeddings.append(vector)
            windows.append((start_ms, end_ms))
        if progress:
            progress(chunk.end_ms, max(total, last_end), "正在分析说话人")
    if not embeddings:
        return fallback_result(FALLBACK_NO_SPEECH)
    labels = cluster_embeddings(embeddings)
    turns = [
        SpeechSegment(
            start_ms=start,
            end_ms=end,
            text="",
            speaker=speaker_id(label),
        )
        for (start, end), label in zip(windows, labels, strict=True)
    ]
    ids = tuple(sorted({item.speaker or "" for item in turns if item.speaker}, key=_speaker_sort))
    return DiarizationResult(
        turns=turns,
        speaker_ids=ids,
        model_id=finder.model_id or model_id(),
        device=finder.device,
        fallback=False,
    )


def label_document(
    document: SubtitleDocument,
    audio_path: Path,
    *,
    embedder: SpeakerEmbedder | None = None,
    progress: ProgressCallback | None = None,
) -> DiarizationResult:
    if not is_speaker_model_ready():
        return fallback_result(FALLBACK_NO_MODEL)
    finder = embedder or SpeakerEmbedder()
    if not finder.available:
        return fallback_result(FALLBACK_NO_MODEL)
    if not document.segments:
        return fallback_result(FALLBACK_NO_SPEECH)
    source = audio_path.expanduser().resolve()
    embeddings: list[np.ndarray] = []
    usable: list[int] = []
    total = max(len(document.segments), 1)
    for index, segment in enumerate(document.segments):
        if progress:
            progress(index, total, f"正在提取第 {index + 1}/{total} 条音色")
        if segment.end_time <= segment.start_time:
            continue
        piece = extract_pcm_window(source, segment.start_time, segment.end_time, accurate_seek=True)
        vector = finder.embed_pcm(piece.pcm_s16le)
        if vector is None:
            continue
        embeddings.append(vector)
        usable.append(index)
    if not embeddings:
        return diarize_media(source, embedder=finder, progress=progress)
    labels = cluster_embeddings(embeddings)
    for index, label in zip(usable, labels, strict=True):
        assign_canonical(document, index, speaker_id(label))
    ensure_speaker_styles(document)
    turns = [
        SpeechSegment(
            start_ms=document.segments[index].start_time,
            end_ms=document.segments[index].end_time,
            text=document.segments[index].display_text(),
            speaker=document.segments[index].speaker,
        )
        for index in usable
    ]
    ids = tuple(
        sorted(
            {str(document.segments[index].extra.get("speaker_id") or "") for index in usable if document.segments[index].extra.get("speaker_id")},
            key=_speaker_sort,
        )
    )
    return DiarizationResult(
        turns=turns,
        speaker_ids=ids,
        model_id=finder.model_id or model_id(),
        device=finder.device,
        fallback=False,
    )


def apply_turns(document: SubtitleDocument, turns: list[SpeechSegment]) -> None:
    for index, segment in enumerate(document.segments):
        speaker = majority_speaker(segment, turns)
        if not speaker:
            continue
        assign_canonical(document, index, speaker)
    ensure_speaker_styles(document)


def _speaker_sort(label: str) -> tuple[int, str]:
    parts = (label or "").split()
    if len(parts) == 2 and parts[1].isdigit():
        return (int(parts[1]), label)
    return (99, label)
