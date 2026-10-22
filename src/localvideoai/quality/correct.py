"""Deterministic subtitle correction. Does not invent wording."""

from __future__ import annotations

import re

from localvideoai.speech.postprocess import correct_text

_DOUBLE_WORD = re.compile(r"(的的|了了|是是|在在|我我|不不好)")
_DOUBLE_PUNCT = re.compile(r"([。！？!?.,，、])\1+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u202e\ufffd]")


def correct_subtitle_text(text: str) -> str:
    cleaned = correct_text(text)
    cleaned = _CONTROL.sub("", cleaned)
    cleaned = _DOUBLE_WORD.sub(lambda match: match.group(1)[:1] if match.group(1) != "不不好" else "不好", cleaned)
    cleaned = _DOUBLE_PUNCT.sub(r"\1", cleaned)
    return cleaned.strip()


def needs_correction(text: str) -> bool:
    return correct_subtitle_text(text) != (text or "").strip()
