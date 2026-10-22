"""Sentence splitting, punctuation cleanup, and basic hallucination correction."""

from __future__ import annotations

import re

from localvideoai.core.types import SpeechSegment, SpeechWord

_ENDERS = frozenset("。！？!?.;；")
_SPACE_RE = re.compile(r"[ \t]+")
_REPEAT_WORD_RE = re.compile(r"\b(\S+)(?:\s+\1){3,}\b", re.IGNORECASE)
_REPEAT_CHAR_RE = re.compile(r"(.)\1{5,}")


def correct_text(text: str) -> str:
    cleaned = (text or "").replace("\u3000", " ").strip()
    cleaned = _REPEAT_WORD_RE.sub(r"\1 \1", cleaned)
    cleaned = _REPEAT_CHAR_RE.sub(r"\1\1\1", cleaned)
    cleaned = _SPACE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?，。！？、])", r"\1", cleaned)
    return cleaned.strip()


def sentences_from_words(words: list[SpeechWord], language: str) -> list[SpeechSegment]:
    if not words:
        return []
    groups: list[list[SpeechWord]] = [[]]
    for word in words:
        groups[-1].append(word)
        token = word.text.strip()
        if token and token[-1] in _ENDERS:
            groups.append([])
    groups = [group for group in groups if group]
    segments: list[SpeechSegment] = []
    for group in groups:
        text = _join_words(group, language)
        text = correct_text(text)
        if not text:
            continue
        confidences = [item.confidence for item in group if item.confidence is not None]
        segments.append(
            SpeechSegment(
                start_ms=group[0].start_ms,
                end_ms=group[-1].end_ms,
                text=text,
                confidence=(sum(confidences) / len(confidences)) if confidences else None,
                language=language,
                words=tuple(group),
            )
        )
    return segments


def fallback_segments(start_ms: int, end_ms: int, text: str, language: str, confidence: float | None) -> list[SpeechSegment]:
    cleaned = correct_text(text)
    if not cleaned:
        return []
    pieces = _split_plain(cleaned)
    if len(pieces) <= 1:
        return [
            SpeechSegment(
                start_ms=start_ms,
                end_ms=end_ms,
                text=cleaned,
                confidence=confidence,
                language=language,
            )
        ]
    span = max(1, end_ms - start_ms)
    out: list[SpeechSegment] = []
    cursor = 0
    total_chars = sum(len(piece) for piece in pieces) or 1
    for piece in pieces:
        width = max(1, int(span * (len(piece) / total_chars)))
        out.append(
            SpeechSegment(
                start_ms=start_ms + cursor,
                end_ms=min(end_ms, start_ms + cursor + width),
                text=piece,
                confidence=confidence,
                language=language,
            )
        )
        cursor += width
    if out:
        last = out[-1]
        out[-1] = SpeechSegment(
            start_ms=last.start_ms,
            end_ms=end_ms,
            text=last.text,
            confidence=last.confidence,
            language=last.language,
            words=last.words,
        )
    return out


def _join_words(words: list[SpeechWord], language: str) -> str:
    if language == "en":
        return " ".join(word.text.strip() for word in words if word.text.strip())
    return "".join(word.text for word in words)


def _split_plain(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", text)
    return [part.strip() for part in parts if part.strip()]
