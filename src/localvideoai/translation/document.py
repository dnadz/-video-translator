"""Apply a TranslationEngine to a subtitle document. Works with any engine that implements translate()."""

from __future__ import annotations

from collections.abc import Callable

from localvideoai.core.exceptions import TranslationError
from localvideoai.core.types import SubtitleSegment, TranslationRequest, TranslationResult
from localvideoai.engines.translation_engine import TranslationEngine
from localvideoai.managers.context_manager import ContextManager
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.language import detect_source_language, normalize_translation_language

ProgressCallback = Callable[[int, int, str], None]


def collect_target_langs(primary: str, extra: list[str] | None = None) -> list[str]:
    langs: list[str] = []
    for item in [primary, *(extra or [])]:
        code = normalize_translation_language(item) or (item or "").strip().lower()
        if code and code not in langs:
            langs.append(code)
    if not langs:
        raise ValueError("至少需要一个目标语言")
    return langs


def translate_document(
    engine: TranslationEngine,
    document: SubtitleDocument,
    source_lang: str,
    target_langs: list[str],
    *,
    quality: str = "standard",
    device_preference: str = "auto",
    prefer_gpu: bool = True,
    progress: ProgressCallback | None = None,
    context_manager: ContextManager | None = None,
    use_context: bool = True,
    batch_size: int = 1,
) -> list[TranslationResult]:
    langs = collect_target_langs(target_langs[0], target_langs[1:])
    primary = langs[0]
    extras = langs[1:]
    total = max(len(document.segments) * len(langs), 1)
    done = 0
    results: list[TranslationResult] = []
    auto = (source_lang or "auto").strip().lower() in {"", "auto", "und", "unknown"}
    manager = _resolve_context_manager(engine, quality, context_manager, use_context)
    cues = [segment.to_cue() for segment in document.segments]
    chunks = manager.chunk_ranges(len(document.segments)) if manager is not None else [range(len(document.segments))]
    context_note = manager.progress_label() if manager is not None else ""
    size = max(1, int(batch_size))
    for chunk in chunks:
        if size > 1 and not extras and hasattr(engine, "translate_many"):
            done = _translate_chunk_batched(
                engine,
                document,
                chunk,
                source_lang,
                primary,
                auto,
                quality,
                device_preference,
                prefer_gpu,
                manager,
                cues,
                size,
                done,
                total,
                context_note,
                progress,
                results,
            )
            continue
        for index in chunk:
            segment = document.segments[index]
            text = segment.display_text().strip()
            if segment.locked:
                if manager is not None:
                    manager.note_source(text)
                done += len(langs)
                if progress:
                    progress(done, total, "跳过已锁定字幕")
                continue
            if not text:
                done += len(langs)
                continue
            detected = detect_source_language(text) if auto else (normalize_translation_language(source_lang) or source_lang)
            if auto:
                recognized = normalize_translation_language(document.detected_language or "")
                if recognized in {"zh", "en", "ja"}:
                    detected = recognized
                elif detected == "und":
                    detected = document.detected_language or "und"
            if detected in {"", "und", "auto", "unknown"}:
                done += len(langs)
                if progress:
                    progress(done, total, "跳过无法判断源语言的字幕")
                continue
            context = manager.build_context(cues, index) if manager is not None else None
            prepared = (
                manager.prepare(text, detected, primary, context or "")
                if manager is not None
                else None
            )
            request_text = prepared.text if prepared is not None else text
            primary_result = engine.translate(
                TranslationRequest(
                    text=request_text,
                    source_lang=detected,
                    target_lang=primary,
                    context=context,
                    quality=quality,
                    device_preference=device_preference,
                    prefer_gpu=prefer_gpu,
                    force_terms=prepared.force_terms if prepared is not None else (),
                    session_memory=prepared.session_memory if prepared is not None else (),
                )
            )
            segment.translated_text = primary_result.text
            segment.language = segment.language or primary_result.source_lang
            if manager is not None:
                manager.observe(text, request_text, primary_result.text, primary)
                segment.extra["context_applied"] = list(prepared.applied) if prepared is not None else []
                segment.extra["context_rewritten"] = request_text
            results.append(primary_result)
            done += 1
            if progress:
                progress(done, total, f"已译 {done}/{total}{context_note}")
            if not extras:
                continue
            translations = dict(segment.extra.get("translations") or {})
            for lang in extras:
                extra_prepared = (
                    manager.prepare(text, detected, lang, context or "")
                    if manager is not None
                    else None
                )
                extra_text = extra_prepared.text if extra_prepared is not None else text
                extra_result = engine.translate(
                    TranslationRequest(
                        text=extra_text,
                        source_lang=detected,
                        target_lang=lang,
                        context=context,
                        quality=quality,
                        device_preference=device_preference,
                        prefer_gpu=prefer_gpu,
                        force_terms=extra_prepared.force_terms if extra_prepared is not None else (),
                        session_memory=extra_prepared.session_memory if extra_prepared is not None else (),
                    )
                )
                translations[lang] = extra_result.text
                if manager is not None:
                    manager.observe(text, extra_text, extra_result.text, lang)
                results.append(extra_result)
                done += 1
                if progress:
                    progress(done, total, f"已译 {done}/{total}{context_note}")
            segment.extra["translations"] = translations
    return results


def _translate_chunk_batched(
    engine: TranslationEngine,
    document: SubtitleDocument,
    chunk: range,
    source_lang: str,
    primary: str,
    auto: bool,
    quality: str,
    device_preference: str,
    prefer_gpu: bool,
    manager,
    cues,
    batch_size: int,
    done: int,
    total: int,
    context_note: str,
    progress: ProgressCallback | None,
    results: list[TranslationResult],
) -> int:
    cursor = chunk.start
    while cursor < chunk.stop:
        indexes: list[int] = []
        while cursor < chunk.stop and len(indexes) < batch_size:
            segment = document.segments[cursor]
            text = segment.display_text().strip()
            if segment.locked or not text:
                if segment.locked and manager is not None:
                    manager.note_source(text)
                done += 1
                if progress and segment.locked:
                    progress(done, total, "跳过已锁定字幕")
                cursor += 1
                continue
            detected = _detected_source(segment, document, source_lang, auto)
            if detected in {"", "und", "auto", "unknown"}:
                done += 1
                if progress:
                    progress(done, total, "跳过无法判断源语言的字幕")
                cursor += 1
                continue
            indexes.append(cursor)
            cursor += 1
        if not indexes:
            continue
        requests: list[TranslationRequest] = []
        prepared_rows = []
        for index in indexes:
            segment = document.segments[index]
            text = segment.display_text().strip()
            detected = _detected_source(segment, document, source_lang, auto)
            context = manager.build_context(cues, index) if manager is not None else None
            prepared = manager.prepare(text, detected, primary, context or "") if manager is not None else None
            request_text = prepared.text if prepared is not None else text
            requests.append(
                TranslationRequest(
                    text=request_text,
                    source_lang=detected,
                    target_lang=primary,
                    context=context,
                    quality=quality,
                    device_preference=device_preference,
                    prefer_gpu=prefer_gpu,
                    force_terms=prepared.force_terms if prepared is not None else (),
                    session_memory=prepared.session_memory if prepared is not None else (),
                )
            )
            prepared_rows.append((segment, text, prepared))
        batch_results = engine.translate_many(requests)
        if len(batch_results) != len(prepared_rows):
            raise TranslationError("批量翻译结果数量和字幕数量不一致")
        for (segment, text, prepared), primary_result in zip(prepared_rows, batch_results, strict=True):
            request_text = prepared.text if prepared is not None else text
            segment.translated_text = primary_result.text
            segment.language = segment.language or primary_result.source_lang
            if manager is not None:
                manager.observe(text, request_text, primary_result.text, primary)
                segment.extra["context_applied"] = list(prepared.applied) if prepared is not None else []
                segment.extra["context_rewritten"] = request_text
            results.append(primary_result)
            done += 1
            if progress:
                progress(done, total, f"已译 {done}/{total}，每批 {batch_size} 句{context_note}")
    return done


def _detected_source(segment: SubtitleSegment, document: SubtitleDocument, source_lang: str, auto: bool) -> str:
    text = segment.display_text().strip()
    detected = detect_source_language(text) if auto else (normalize_translation_language(source_lang) or source_lang)
    if auto:
        recognized = normalize_translation_language(document.detected_language or "")
        if recognized in {"zh", "en", "ja"}:
            detected = recognized
        elif detected == "und":
            detected = document.detected_language or "und"
    return detected


def _resolve_context_manager(
    engine: TranslationEngine,
    quality: str,
    context_manager: ContextManager | None,
    use_context: bool,
):
    if not use_context:
        return None
    if context_manager is not None:
        return context_manager
    from localvideoai.managers.local_context_manager import create_context_manager

    resources = getattr(engine, "_resources", None)
    return create_context_manager(quality, resources=resources)


def first_source_text(segments: list[SubtitleSegment]) -> str:
    parts = [item.display_text() for item in segments if item.display_text().strip()]
    return "\n".join(parts[:12])
