"""Headless path used by the packaged EXE. Same engines as the two buttons."""

from __future__ import annotations

from pathlib import Path


def run_smoke(media: str) -> int:
    source = Path(media).expanduser()
    if not source.is_file():
        print(f"FAIL: missing {source}")
        return 2
    from localvideoai.engines.ctranslate2_translation_engine import CTranslate2TranslationEngine
    from localvideoai.engines.faster_whisper_engine import FasterWhisperSpeechEngine
    from localvideoai.speech.persist import transcript_to_document

    from simplecaption.srtio import save_role_srt

    transcript = FasterWhisperSpeechEngine().transcribe_media(
        source,
        language="en",
        device_preference="auto",
        prefer_gpu=True,
    )
    print(f"segments={len(transcript.segments)} lang={transcript.language} model={transcript.model_id}/{transcript.device}")
    for item in transcript.segments:
        print(f"{item.start_ms}-{item.end_ms} {item.text}")
    if not transcript.segments:
        print("FAIL: no segments")
        return 1
    document = transcript_to_document(transcript)
    CTranslate2TranslationEngine().translate_document(
        document,
        "en",
        ["zh"],
        quality="standard",
        device_preference="auto",
        prefer_gpu=True,
    )
    texts = [item.translated_text.strip() for item in document.segments if item.translated_text.strip()]
    if not texts:
        print("FAIL: empty translation")
        return 1
    for text in texts:
        print(text)
    saved = save_role_srt(document, source.with_suffix(".zh.srt"), "translated")
    print(f"srt={saved}")
    return 0
