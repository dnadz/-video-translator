"""Group OCR boxes into lines and merge consecutive identical cues."""

from __future__ import annotations

from difflib import SequenceMatcher

from localvideoai.core.types import OCRBox, OCRCue
from localvideoai.ocr.language import detect_script_language
from localvideoai.ocr.region import union_norm_box


def boxes_to_cue(
    boxes: list[OCRBox],
    start_ms: int,
    end_ms: int,
    language: str | None = None,
) -> OCRCue | None:
    usable = [item for item in boxes if item.text.strip()]
    if not usable:
        return None
    lines = _cluster_lines(usable)
    text = "\n".join(_join_line(line) for line in lines).strip()
    if not text:
        return None
    confidences = [item.confidence for item in usable if item.confidence is not None]
    all_points = tuple(point for item in usable for point in item.points)
    if all_points:
        x0, y0, x1, y1 = union_norm_box(all_points)
    else:
        x0, y0, x1, y1 = 0.0, 0.0, 1.0, 1.0
    lang = language or detect_script_language(text)
    return OCRCue(
        start_ms=start_ms,
        end_ms=max(end_ms, start_ms),
        text=text,
        confidence=(sum(confidences) / len(confidences)) if confidences else None,
        language=lang,
        x=x0,
        y=y0,
        w=max(0.0, x1 - x0),
        h=max(0.0, y1 - y0),
        boxes=tuple(usable),
    )


def text_similar(left: str, right: str, threshold: float = 0.86) -> bool:
    a = _normalize_compare(left)
    b = _normalize_compare(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def merge_cues(cues: list[OCRCue], gap_ms: int = 500) -> list[OCRCue]:
    if not cues:
        return []
    ordered = sorted(cues, key=lambda item: (item.start_ms, item.end_ms))
    merged: list[OCRCue] = [ordered[0]]
    for item in ordered[1:]:
        last = merged[-1]
        close = item.start_ms <= last.end_ms + gap_ms
        if close and text_similar(last.text, item.text):
            merged[-1] = OCRCue(
                start_ms=last.start_ms,
                end_ms=max(last.end_ms, item.end_ms),
                text=last.text if len(last.text) >= len(item.text) else item.text,
                confidence=_avg_conf(last.confidence, item.confidence),
                language=last.language or item.language,
                x=min(last.x, item.x),
                y=min(last.y, item.y),
                w=max(last.x + last.w, item.x + item.w) - min(last.x, item.x),
                h=max(last.y + last.h, item.y + item.h) - min(last.y, item.y),
                boxes=last.boxes + item.boxes,
            )
        else:
            merged.append(item)
    return merged


def _cluster_lines(boxes: list[OCRBox]) -> list[list[OCRBox]]:
    items = sorted(boxes, key=lambda item: (_center_y(item), _center_x(item)))
    lines: list[list[OCRBox]] = []
    for box in items:
        if not lines:
            lines.append([box])
            continue
        current = lines[-1]
        ref = current[0]
        height = max(_box_h(ref), _box_h(box), 0.02)
        if abs(_center_y(box) - _center_y(ref)) <= height * 0.65:
            current.append(box)
        else:
            lines.append([box])
    for line in lines:
        line.sort(key=_center_x)
    return lines


def _join_line(boxes: list[OCRBox]) -> str:
    parts = [item.text.strip() for item in boxes if item.text.strip()]
    if not parts:
        return ""
    if all(_mostly_latin(part) for part in parts):
        return " ".join(parts)
    return "".join(parts)


def _mostly_latin(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    latin = sum(1 for ch in letters if "A" <= ch <= "Z" or "a" <= ch <= "z")
    return latin / len(letters) >= 0.6


def _center_x(box: OCRBox) -> float:
    if not box.points:
        return 0.0
    return sum(point[0] for point in box.points) / len(box.points)


def _center_y(box: OCRBox) -> float:
    if not box.points:
        return 0.0
    return sum(point[1] for point in box.points) / len(box.points)


def _box_h(box: OCRBox) -> float:
    if not box.points:
        return 0.04
    ys = [point[1] for point in box.points]
    return max(ys) - min(ys)


def _normalize_compare(text: str) -> str:
    return "".join(text.lower().split())


def _avg_conf(left: float | None, right: float | None) -> float | None:
    values = [item for item in (left, right) if item is not None]
    if not values:
        return None
    return sum(values) / len(values)
