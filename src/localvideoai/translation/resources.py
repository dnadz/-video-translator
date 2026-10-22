"""Glossary, translation memory, and character dictionary. User files override bundled."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from localvideoai.core.exceptions import TranslationError
from localvideoai.core.paths import ensure_directory, install_root, translation_user_dir
from localvideoai.translation.language import normalize_translation_language

Kind = Literal["glossary", "translation_memory", "character_dictionary"]

FILE_NAMES: dict[Kind, str] = {
    "glossary": "glossary.json",
    "translation_memory": "translation_memory.json",
    "character_dictionary": "character_dictionary.json",
}


@dataclass
class ResourceEntry:
    source: str
    target: str
    source_lang: str = ""
    target_lang: str = ""
    note: str = ""
    origin: str = "user"

    def key(self) -> tuple[str, str, str]:
        return (self.source, self.source_lang, self.target_lang)

    def to_json(self) -> dict[str, str]:
        payload = {
            "source": self.source,
            "target": self.target,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
        }
        if self.note:
            payload["note"] = self.note
        return payload

    def applies_to(self, source_lang: str, target_lang: str) -> bool:
        src_ok = not self.source_lang or self.source_lang == source_lang
        tgt_ok = not self.target_lang or self.target_lang == target_lang
        return src_ok and tgt_ok


@dataclass
class TranslationResources:
    user_dir: Path = field(default_factory=translation_user_dir)

    def bundled_dir(self) -> Path:
        from localvideoai.core.paths import bundle_root, install_root

        for root in (install_root(), bundle_root()):
            candidate = root / "config" / "translation"
            if candidate.is_dir():
                return candidate
        return install_root() / "config" / "translation"

    def user_path(self, kind: Kind) -> Path:
        return self.user_dir / FILE_NAMES[kind]

    def bundled_path(self, kind: Kind) -> Path:
        return self.bundled_dir() / FILE_NAMES[kind]

    def load_user(self, kind: Kind) -> list[ResourceEntry]:
        return _load_entries(self.user_path(kind), origin="user")

    def load_bundled(self, kind: Kind) -> list[ResourceEntry]:
        return _load_entries(self.bundled_path(kind), origin="bundled")

    def merged(self, kind: Kind) -> list[ResourceEntry]:
        merged: dict[tuple[str, str, str], ResourceEntry] = {}
        for entry in self.load_bundled(kind):
            merged[entry.key()] = entry
        for entry in self.load_user(kind):
            merged[entry.key()] = entry
        return list(merged.values())

    def save_user(self, kind: Kind, entries: list[ResourceEntry]) -> Path:
        path = self.user_path(kind)
        ensure_directory(path.parent)
        payload = {
            "schema": 1,
            "kind": kind,
            "entries": [entry.to_json() for entry in entries if entry.source.strip()],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def matching(self, kind: Kind, source_lang: str, target_lang: str) -> list[ResourceEntry]:
        return [
            entry
            for entry in self.merged(kind)
            if entry.applies_to(source_lang, target_lang) and entry.source.strip()
        ]

    def lookup_memory(self, text: str, source_lang: str, target_lang: str) -> ResourceEntry | None:
        needle = (text or "").strip()
        if not needle:
            return None
        user_hit = _lookup(self.load_user("translation_memory"), needle, source_lang, target_lang)
        if user_hit is not None:
            return user_hit
        return _lookup(self.load_bundled("translation_memory"), needle, source_lang, target_lang)


def _lookup(
    entries: list[ResourceEntry],
    text: str,
    source_lang: str,
    target_lang: str,
) -> ResourceEntry | None:
    folded = text.casefold()
    exact: ResourceEntry | None = None
    loose: ResourceEntry | None = None
    for entry in entries:
        if not entry.applies_to(source_lang, target_lang):
            continue
        if entry.source.strip() == text:
            exact = entry
            break
        if entry.source.strip().casefold() == folded:
            loose = loose or entry
    return exact or loose


def _load_entries(path: Path, origin: str) -> list[ResourceEntry]:
    if not path.is_file():
        return []
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TranslationError(f"词表文件不是有效 JSON：{path}") from exc
    raw_entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(raw_entries, list):
        raise TranslationError(f"词表文件缺少 entries 数组：{path}")
    entries: list[ResourceEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        if not source:
            continue
        entries.append(
            ResourceEntry(
                source=source,
                target=str(item.get("target") or ""),
                source_lang=normalize_translation_language(str(item.get("source_lang") or "")) or "",
                target_lang=normalize_translation_language(str(item.get("target_lang") or "")) or "",
                note=str(item.get("note") or ""),
                origin=origin,
            )
        )
    return entries
