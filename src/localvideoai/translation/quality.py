"""Map UI quality tiers to decoding settings. Not a fake delay."""

from __future__ import annotations

QUALITY_BEAM = {
    "fast": 1,
    "standard": 2,
    "high": 5,
}

QUALITY_ALIASES = {
    "fast": "fast",
    "极速": "fast",
    "speed": "fast",
    "standard": "standard",
    "标准": "standard",
    "normal": "standard",
    "high": "high",
    "高质量": "high",
    "quality": "high",
    "best": "high",
}


def normalize_quality(value: str | None) -> str:
    key = (value or "standard").strip().lower()
    return QUALITY_ALIASES.get(key, QUALITY_ALIASES.get(value or "", "standard"))


def beam_size_for(quality: str | None) -> int:
    return QUALITY_BEAM[normalize_quality(quality)]
