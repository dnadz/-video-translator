"""Identify subtitle language from container tags and cue text. Fully local."""

from __future__ import annotations

LANGUAGE_LABELS = {
    "zh": "中文",
    "en": "英文",
    "ja": "日文",
    "und": "未识别",
}

_ALIASES = {
    "zh": "zh",
    "chi": "zh",
    "zho": "zh",
    "cmn": "zh",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "zh-tw": "zh",
    "zh-hant": "zh",
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


def normalize_language_tag(value: str | None) -> str:
    if value is None:
        return ""
    key = value.strip().lower().replace("_", "-")
    if not key or key in {"und", "unknown", "unk", "none"}:
        return ""
    if key in _ALIASES:
        return _ALIASES[key]
    primary = key.split("-", 1)[0]
    return _ALIASES.get(primary, primary)


def language_display_name(code: str) -> str:
    key = normalize_language_tag(code) or (code.strip().lower() if code else "und")
    if key in LANGUAGE_LABELS:
        return LANGUAGE_LABELS[key]
    return code or "und"


def detect_script_language(text: str) -> str:
    hiragana = 0
    katakana = 0
    cjk = 0
    latin = 0
    for char in text:
        code = ord(char)
        if 0x3040 <= code <= 0x309F:
            hiragana += 1
        elif 0x30A0 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF:
            katakana += 1
        elif 0x4E00 <= code <= 0x9FFF:
            cjk += 1
        elif "A" <= char <= "Z" or "a" <= char <= "z":
            latin += 1
    kana = hiragana + katakana
    if kana >= 1:
        return "ja"
    if cjk >= 1:
        return "zh"
    if latin >= 1:
        return "en"
    return ""


def identify_language(text: str, container_language: str | None = None) -> str:
    tagged = normalize_language_tag(container_language)
    detected = detect_script_language(text)
    return tagged or detected or "und"
