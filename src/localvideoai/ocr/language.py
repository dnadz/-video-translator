"""Detect Chinese / English / Japanese from OCR text. Fully local."""

from __future__ import annotations

import re

from localvideoai.speech.language import normalize_speech_language

_KANA = re.compile(r"[\u3040-\u30ff]")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")


def normalize_ocr_language(value: str | None) -> str | None:
    return normalize_speech_language(value)


def detect_script_language(text: str) -> str:
    blob = text or ""
    if _KANA.search(blob):
        return "ja"
    if _CJK.search(blob):
        return "zh"
    if _LATIN.search(blob):
        return "en"
    return "und"
