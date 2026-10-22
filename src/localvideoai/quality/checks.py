"""Deterministic subtitle QA checks. Thresholds follow common broadcast practice."""

from __future__ import annotations

import re
from localvideoai.core.types import SubtitleSegment
from localvideoai.quality.correct import needs_correction
from localvideoai.quality.metrics import cps_of, display_chars, duration_ms, is_cjk
from localvideoai.quality.types import QualityIssue
from localvideoai.subtitles.lock import ranges_overlap
from localvideoai.translation.resources import ResourceEntry, TranslationResources

MIN_DURATION_MS = 833
MAX_DURATION_MS = 7000
MAX_LINES = 2
MAX_CHARS_LINE_LATIN = 42
MAX_CHARS_LINE_CJK = 21
CPS_LIMIT_LATIN = 17.0
CPS_LIMIT_CJK = 13.0
SAFE_MARGIN = 0.05
_ABNORMAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u202e\ufffd]|ZZ[A-Z]?\d*Z*")


def inspect_segment(
    segments: list[SubtitleSegment],
    index: int,
    *,
    expect_translation: bool,
    resources: TranslationResources | None = None,
) -> list[QualityIssue]:
    segment = segments[index]
    text = segment.display_text()
    issues: list[QualityIssue] = []
    if needs_correction(text) or needs_correction(segment.source_text):
        issues.append(_issue(index, segment, "typo", "疑似错别字或重复字词", 12))
    if expect_translation and text.strip() and not segment.translated_text.strip():
        issues.append(_issue(index, segment, "missing_translation", "翻译缺失", 25))
    for other in segments:
        if other is segment:
            continue
        if ranges_overlap(segment, other):
            issues.append(_issue(index, segment, "overlap", f"与 #{other.id} 时间重叠", 18))
            break
    span = duration_ms(segment)
    if text.strip() and span < MIN_DURATION_MS:
        issues.append(_issue(index, segment, "too_short", f"字幕过短（{span} ms）", 12))
    if span > MAX_DURATION_MS:
        issues.append(_issue(index, segment, "too_long", f"字幕过长（{span} ms）", 10))
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > MAX_LINES:
        issues.append(_issue(index, segment, "too_long", f"超过 {MAX_LINES} 行", 10))
    limit = MAX_CHARS_LINE_CJK if is_cjk(text) else MAX_CHARS_LINE_LATIN
    if any(display_chars(line) > limit for line in (lines or [text])):
        issues.append(_issue(index, segment, "too_long", f"单行超过 {limit} 字", 8))
    cps = cps_of(segment)
    cps_limit = CPS_LIMIT_CJK if is_cjk(text) else CPS_LIMIT_LATIN
    if text.strip() and cps > cps_limit:
        issues.append(_issue(index, segment, "cps", f"阅读速度 {cps:.1f} CPS，超过 {cps_limit:.0f}", 14))
        issues.append(_issue(index, segment, "reading_speed", f"阅读速度过快（{cps:.1f} 字/秒）", 8))
    if _outside_safe_area(segment):
        issues.append(_issue(index, segment, "safe_area", "超出安全区域", 10))
    if _ABNORMAL.search(text) or _ABNORMAL.search(segment.translated_text):
        issues.append(_issue(index, segment, "abnormal", "异常字符或未还原占位符", 16))
    issues.extend(_consistency_issues(segments, index, resources))
    return issues


def _consistency_issues(
    segments: list[SubtitleSegment],
    index: int,
    resources: TranslationResources | None,
) -> list[QualityIssue]:
    if resources is None:
        return []
    segment = segments[index]
    source = segment.display_text()
    translated = segment.translated_text
    if not source.strip() or not translated.strip():
        return []
    entries = _term_entries(resources)
    for entry in entries:
        if entry.source not in source or not entry.target:
            continue
        if entry.target in translated:
            continue
        others = [
            item
            for item in segments
            if item is not segment and entry.source in item.display_text() and item.translated_text.strip()
        ]
        if any(entry.target in item.translated_text for item in others):
            return [_issue(index, segment, "consistency", f"术语「{entry.source}」译法不一致", 15)]
    return []


def document_term_consistency(segments: list[SubtitleSegment], resources: TranslationResources | None) -> dict[int, float]:
    scores = {index: 100.0 for index in range(len(segments))}
    if resources is None:
        return scores
    entries = _term_entries(resources)
    for index, segment in enumerate(segments):
        source = segment.display_text()
        translated = segment.translated_text
        if not translated.strip():
            continue
        for entry in entries:
            if entry.source not in source or not entry.target:
                continue
            if entry.target in translated:
                continue
            others = [
                item
                for item in segments
                if item is not segment and entry.source in item.display_text() and item.translated_text.strip()
            ]
            if any(entry.target in item.translated_text for item in others):
                scores[index] = 55.0
                break
    return scores


def _term_entries(resources: TranslationResources) -> list[ResourceEntry]:
    merged: dict[str, ResourceEntry] = {}
    for kind in ("glossary", "character_dictionary"):
        for entry in resources.merged(kind):
            if entry.source.strip() and entry.target.strip():
                merged[entry.source] = entry
    return sorted(merged.values(), key=lambda item: len(item.source), reverse=True)


def _outside_safe_area(segment: SubtitleSegment) -> bool:
    box = segment.extra.get("ocr") if isinstance(segment.extra, dict) else None
    if not isinstance(box, dict):
        return False
    try:
        x = float(box.get("x", 0.0))
        y = float(box.get("y", 0.0))
        width = float(box.get("w", 1.0))
        height = float(box.get("h", 1.0))
    except (TypeError, ValueError):
        return False
    return x < SAFE_MARGIN or y < SAFE_MARGIN or x + width > 1 - SAFE_MARGIN or y + height > 1 - SAFE_MARGIN


def _issue(index: int, segment: SubtitleSegment, code: str, message: str, penalty: int) -> QualityIssue:
    return QualityIssue(code=code, message=message, penalty=penalty, cue_index=index, cue_id=segment.id)
