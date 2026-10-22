"""Convert model confidence and text stats into 0–100 scores."""

from __future__ import annotations

import math
import re

from localvideoai.core.types import SubtitleSegment

_HAN = re.compile(r"[\u3400-\u9fff]")


def display_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def duration_ms(segment: SubtitleSegment) -> int:
    return max(0, int(segment.end_time) - int(segment.start_time))


def cps_of(segment: SubtitleSegment) -> float:
    span = duration_ms(segment) / 1000.0
    if span <= 0:
        return 999.0 if display_chars(segment.display_text()) else 0.0
    return display_chars(segment.display_text()) / span


def is_cjk(text: str) -> bool:
    return bool(_HAN.search(text or ""))


def recognition_score(confidence: float | None, has_text: bool) -> float:
    if not has_text:
        return 0.0
    if confidence is None:
        return 80.0
    value = float(confidence)
    if 0.0 <= value <= 1.0:
        return max(0.0, min(100.0, value * 100.0))
    if value < 0:
        return max(0.0, min(100.0, math.exp(value) * 100.0))
    if value <= 100.0:
        return max(0.0, min(100.0, value))
    return 80.0


def translation_score(source: str, translated: str, *, expect_translation: bool) -> float:
    src = (source or "").strip()
    dst = (translated or "").strip()
    if not src:
        return 100.0
    if not expect_translation and not dst:
        return 100.0
    if not dst:
        return 0.0
    if dst == src:
        return 35.0
    if "ZZ" in dst:
        return 40.0
    src_n = max(1, display_chars(src))
    dst_n = display_chars(dst)
    ratio = dst_n / src_n
    if is_cjk(src) and not is_cjk(dst):
        good = 0.6 <= ratio <= 3.5
    elif is_cjk(dst) and not is_cjk(src):
        good = 0.25 <= ratio <= 1.8
    else:
        good = 0.4 <= ratio <= 2.8
    return 92.0 if good else 62.0
