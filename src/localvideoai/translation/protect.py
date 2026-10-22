"""Protect glossary / character terms with placeholders the MT model should copy."""

from __future__ import annotations

import re
from dataclasses import dataclass

from localvideoai.translation.resources import ResourceEntry


@dataclass
class Protection:
    text: str
    mapping: dict[str, str]
    hits: int


def protect_terms(text: str, entries: list[ResourceEntry], prefix: str) -> Protection:
    if not text or not entries:
        return Protection(text, {}, 0)
    remaining = text
    mapping: dict[str, str] = {}
    ordered = sorted(entries, key=lambda item: len(item.source), reverse=True)
    for index, entry in enumerate(ordered):
        source = entry.source
        if not source or source not in remaining:
            continue
        token = f"ZZ{prefix}{index}ZZ"
        remaining = remaining.replace(source, token)
        mapping[token] = entry.target or source
    return Protection(remaining, mapping, len(mapping))


def restore_terms(text: str, mapping: dict[str, str]) -> str:
    restored = text or ""
    ordered = sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True)
    for token, target in ordered:
        restored = restored.replace(token, target)
        spaced = re.sub(r"(?<=\w)_(?=\w)", " ", token) if "_" in token else token
        if spaced != token:
            restored = restored.replace(spaced, target)
        restored = restored.replace(token.replace("_", " "), target)
        if token.endswith("ZZ") and len(token) > 4:
            restored = restored.replace(token[:-1], target)
            restored = restored.replace(token[:-2], target)
    unused = [target for target in mapping.values() if target and target not in restored]
    if unused:
        debris = re.compile(r"ZZ[A-Z]?\d*Z*")
        for target in unused:
            restored, count = debris.subn(target, restored, count=1)
            if count == 0:
                break
    return restored
