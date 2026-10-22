"""One realtime window: extract → local ASR → local translation. No UI."""

from __future__ import annotations

import time
from pathlib import Path

from localvideoai.core.exceptions import SpeechError, TranslationError
from localvideoai.core.types import TranslationRequest
from localvideoai.engines.speech_engine import SpeechEngine
from localvideoai.engines.translation_engine import TranslationEngine
from localvideoai.realtime.policy import LatencyProfile, adjust_window_ms, profile_settings
from localvideoai.realtime.types import RealtimeCue
from localvideoai.speech.language import normalize_speech_language
from localvideoai.speech.store import list_local_models
from localvideoai.translation.language import detect_source_language, normalize_translation_language


def process_realtime_window(
    media_path: Path,
    start_ms: int,
    requested_ms: int,
    *,
    speech_engine: SpeechEngine,
    translation_engine: TranslationEngine,
    source_lang: str = "auto",
    target_lang: str = "zh",
    profile: str = "balanced",
    device_preference: str = "auto",
    prefer_gpu: bool = True,
    last_process_ms: int | None = None,
    duration_ms: int | None = None,
) -> RealtimeCue:
    settings = profile_settings(profile)
    window_ms = adjust_window_ms(requested_ms, settings, last_process_ms)
    start = max(0, int(start_ms))
    end = start + window_ms
    if duration_ms is not None:
        end = min(end, max(start + 50, int(duration_ms)))
    transcribe_window = getattr(speech_engine, "transcribe_window", None)
    if transcribe_window is None:
        raise SpeechError("当前语音引擎不支持实时窗口识别")
    model_id = _model_override(settings)
    target = normalize_translation_language(target_lang) or "zh"
    source = normalize_speech_language(source_lang) if source_lang not in {None, "", "auto"} else None
    started = time.perf_counter()
    segments = transcribe_window(
        media_path,
        start,
        end,
        language=source,
        device_preference=device_preference,
        prefer_gpu=prefer_gpu,
        beam_size=settings.asr_beam,
        word_timestamps=settings.word_timestamps,
        accurate_seek=settings.accurate_seek,
        model_id=model_id,
    )
    source_text = " ".join((item.text or "").strip() for item in segments if (item.text or "").strip()).strip()
    detected = source or (segments[0].language if segments else None) or detect_source_language(source_text)
    translated = ""
    if source_text:
        request_source = normalize_translation_language(detected) or "auto"
        if request_source == "und":
            request_source = "auto"
        try:
            result = translation_engine.translate(
                TranslationRequest(
                    source_text,
                    request_source,
                    target,
                    quality=settings.translation_quality,
                    device_preference=device_preference,
                    prefer_gpu=prefer_gpu,
                )
            )
            translated = (result.text or "").strip()
        except TranslationError:
            translated = ""
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    model_name = ""
    device_name = ""
    loaded = getattr(speech_engine, "_loaded_choice", None)
    if loaded is not None:
        model_name = getattr(loaded, "model_id", "") or ""
        device_name = getattr(loaded, "device", "") or ""
    return RealtimeCue(
        start_ms=start,
        end_ms=end,
        source_text=source_text,
        translated_text=translated,
        source_lang=detected or "und",
        target_lang=target,
        window_ms=end - start,
        process_ms=elapsed_ms,
        requested_ms=int(requested_ms),
        profile=settings.profile_id,
        speech_device=device_name,
        model_id=model_name,
    )


def _model_override(settings: LatencyProfile) -> str | None:
    if not settings.prefer_tiny:
        return None
    available = set(list_local_models())
    if "tiny" in available:
        return "tiny"
    return None
