"""Normalize English source text so OPUS-MT does not hallucinate on contractions."""

from __future__ import annotations

import re

_CONTRACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bit's\b", re.I), "it is"),
    (re.compile(r"\bi'm\b", re.I), "I am"),
    (re.compile(r"\bi've\b", re.I), "I have"),
    (re.compile(r"\bi'll\b", re.I), "I will"),
    (re.compile(r"\bi'd\b", re.I), "I would"),
    (re.compile(r"\byou're\b", re.I), "you are"),
    (re.compile(r"\byou've\b", re.I), "you have"),
    (re.compile(r"\byou'll\b", re.I), "you will"),
    (re.compile(r"\bwe're\b", re.I), "we are"),
    (re.compile(r"\bwe've\b", re.I), "we have"),
    (re.compile(r"\bthey're\b", re.I), "they are"),
    (re.compile(r"\bthat's\b", re.I), "that is"),
    (re.compile(r"\bthere's\b", re.I), "there is"),
    (re.compile(r"\bwhat's\b", re.I), "what is"),
    (re.compile(r"\bwho's\b", re.I), "who is"),
    (re.compile(r"\blet's\b", re.I), "let us"),
    (re.compile(r"\bdon't\b", re.I), "do not"),
    (re.compile(r"\bdoesn't\b", re.I), "does not"),
    (re.compile(r"\bdidn't\b", re.I), "did not"),
    (re.compile(r"\bcan't\b", re.I), "cannot"),
    (re.compile(r"\bwon't\b", re.I), "will not"),
    (re.compile(r"\bisn't\b", re.I), "is not"),
    (re.compile(r"\baren't\b", re.I), "are not"),
    (re.compile(r"\bwasn't\b", re.I), "was not"),
    (re.compile(r"\bweren't\b", re.I), "were not"),
    (re.compile(r"\bhaven't\b", re.I), "have not"),
    (re.compile(r"\bhasn't\b", re.I), "has not"),
    (re.compile(r"\bhadn't\b", re.I), "had not"),
)

_HALLUCINATION_MARKERS = ("善财", "优婆塞", "今时", "晨报")
_LATIN = re.compile(r"[A-Za-z]{2,}")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_TRAILING_PUNCT = re.compile(r"[.!?。！？]+$")


def expand_english_contractions(text: str) -> str:
    blob = (text or "").replace("\u2019", "'").replace("`", "'")
    for pattern, replacement in _CONTRACTIONS:
        blob = pattern.sub(replacement, blob)
    return re.sub(r"\s+", " ", blob).strip()


def strip_terminal_punct(text: str) -> str:
    return _TRAILING_PUNCT.sub("", (text or "").strip()).strip()


def english_source_variants(text: str) -> list[str]:
    original = (text or "").strip()
    expanded = expand_english_contractions(original)
    variants: list[str] = []
    for candidate in (
        expanded,
        strip_terminal_punct(expanded),
        strip_terminal_punct(original),
        original,
    ):
        item = (candidate or "").strip()
        if item and item not in variants:
            variants.append(item)
    return variants or [original]


def looks_broken_zh(target: str) -> bool:
    blob = (target or "").strip()
    if not blob:
        return True
    if any(marker in blob for marker in _HALLUCINATION_MARKERS):
        return True
    if _LATIN.search(blob) and _CJK.search(blob):
        return True
    return False
