"""Normalize and detect translation language codes. Fully local."""

from __future__ import annotations

from localvideoai.ocr.language import detect_script_language
from localvideoai.speech.language import normalize_speech_language

SUPPORTED_CORE = ("zh", "en", "ja")


def normalize_translation_language(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().lower().replace("_", "-")
    if key in {"zh-cn", "zh-hans", "zh-sg"}:
        return "zh"
    if key in {"zh-tw", "zh-hk", "zh-hant", "zt"}:
        return "zh"
    return normalize_speech_language(value)


def detect_source_language(text: str) -> str:
    detected = detect_script_language(text)
    if detected == "und":
        return "und"
    return detected


def language_label(code: str | None) -> str:
    normalized = normalize_translation_language(code) or "auto"
    return {"zh": "中文", "en": "英文", "ja": "日文", "auto": "自动", "und": "未知"}.get(
        normalized, normalized
    )
