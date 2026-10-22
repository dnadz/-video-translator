"""Normalize speech language codes for Whisper."""

from __future__ import annotations

_ALIASES = {
    "zh": "zh",
    "chi": "zh",
    "zho": "zh",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "chinese": "zh",
    "en": "en",
    "eng": "en",
    "en-us": "en",
    "en-gb": "en",
    "english": "en",
    "ja": "ja",
    "jpn": "ja",
    "jp": "ja",
    "japanese": "ja",
}


def normalize_speech_language(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().lower().replace("_", "-")
    if not key or key in {"auto", "und", "unknown", "none"}:
        return None
    if key in _ALIASES:
        return _ALIASES[key]
    primary = key.split("-", 1)[0]
    return _ALIASES.get(primary, primary)


def language_label(code: str | None) -> str:
    normalized = normalize_speech_language(code) or "auto"
    return {"zh": "中文", "en": "英文", "ja": "日文", "auto": "自动"}.get(normalized, normalized)
