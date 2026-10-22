"""Local translation context windows, chunking, and session memories.

OPUS-MT is sentence-level. Surrounding sentences are not prepended to the model
input (that usually hurts). Context changes the prepared source, protection
terms, and in-session translation memory instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from localvideoai.core.types import SubtitleCue
from localvideoai.translation.quality import normalize_quality
from localvideoai.translation.resources import ResourceEntry, TranslationResources

_EN_FEMALE = ("she", "her", "hers")
_EN_MALE = ("he", "him", "his")
_ZH_FEMALE = ("她",)
_ZH_MALE = ("他",)
_JA_FEMALE = ("彼女",)
_JA_MALE = ("彼",)


@dataclass(frozen=True)
class ContextWindowPolicy:
    name: str
    label: str
    prev: int
    next: int
    chunk_size: int
    max_chars: int


POLICIES: dict[str, ContextWindowPolicy] = {
    "fast": ContextWindowPolicy("fast", "极速小上下文", prev=2, next=0, chunk_size=40, max_chars=180),
    "standard": ContextWindowPolicy("standard", "标准中上下文", prev=6, next=1, chunk_size=120, max_chars=480),
    "high": ContextWindowPolicy("high", "高质量大上下文", prev=16, next=2, chunk_size=240, max_chars=1200),
}


@dataclass
class PreparedUtterance:
    text: str
    original: str
    context: str
    force_terms: tuple[tuple[str, str], ...]
    session_memory: tuple[tuple[str, str], ...]
    applied: tuple[str, ...]
    pronoun_rewritten: bool


@dataclass
class SessionMemory:
    characters: dict[str, ResourceEntry] = field(default_factory=dict)
    terms: dict[str, ResourceEntry] = field(default_factory=dict)
    places: dict[str, ResourceEntry] = field(default_factory=dict)
    translations: dict[tuple[str, str], str] = field(default_factory=dict)
    last_person: ResourceEntry | None = None
    last_place: ResourceEntry | None = None


def window_policy(quality: str | None) -> ContextWindowPolicy:
    return POLICIES[normalize_quality(quality)]


def context_hint_for(quality: str | None) -> str:
    policy = window_policy(quality)
    nxt = f" + 后 {policy.next} 条" if policy.next else ""
    return f"{policy.label}：前 {policy.prev} 条{nxt}，长字幕每 {policy.chunk_size} 条分块。"


def chunk_ranges(count: int, chunk_size: int) -> list[range]:
    size = max(1, int(chunk_size))
    total = max(0, int(count))
    return [range(start, min(total, start + size)) for start in range(0, total, size)]


def gender_of(entry: ResourceEntry | None) -> str:
    if entry is None:
        return ""
    note = (entry.note or "").lower()
    if "gender=female" in note or "female" in note:
        return "female"
    if "gender=male" in note or "male" in note:
        return "male"
    return ""


def is_person_entry(entry: ResourceEntry) -> bool:
    note = (entry.note or "").lower()
    return "person" in note or "gender=" in note or "character" in note


def is_place_entry(entry: ResourceEntry) -> bool:
    note = (entry.note or "").lower()
    return "place" in note or "location" in note


class TranslationContextSession:
    """Holds character / term / translation memory for one document pass."""

    def __init__(
        self,
        quality: str = "standard",
        *,
        resources: TranslationResources | None = None,
        extra_entries: list[ResourceEntry] | None = None,
        enabled: bool = True,
    ) -> None:
        self.policy = window_policy(quality)
        self.enabled = enabled
        self.memory = SessionMemory()
        self._seed(resources, extra_entries or [])

    def progress_label(self) -> str:
        if not self.enabled:
            return ""
        return f"（{self.policy.label}，前{self.policy.prev}条）"

    def chunk_ranges(self, count: int) -> list[range]:
        if not self.enabled:
            return [range(count)] if count else []
        return chunk_ranges(count, self.policy.chunk_size)

    def build_context(self, cues: list[SubtitleCue], index: int) -> str:
        if not self.enabled or not cues:
            return ""
        if index < 0 or index >= len(cues):
            return ""
        start = max(0, index - self.policy.prev)
        end = min(len(cues), index + 1 + self.policy.next)
        parts: list[str] = []
        for cursor in range(start, end):
            if cursor == index:
                continue
            cue = cues[cursor]
            tag = "PREV" if cursor < index else "NEXT"
            speaker = f"{cue.speaker}: " if cue.speaker else ""
            text = (cue.text or "").strip()
            if text:
                parts.append(f"{tag} {speaker}{text}")
        blob = "\n".join(parts)
        if len(blob) > self.policy.max_chars:
            blob = blob[-self.policy.max_chars :]
        return blob

    def note_source(self, text: str) -> None:
        if not self.enabled:
            return
        self._update_mentions(text)

    def prepare(self, text: str, source_lang: str, target_lang: str, context: str = "") -> PreparedUtterance:
        original = text or ""
        if not self.enabled:
            return PreparedUtterance(
                text=original,
                original=original,
                context="",
                force_terms=(),
                session_memory=(),
                applied=(),
                pronoun_rewritten=False,
            )
        previous_person = self.memory.last_person
        rewritten, pronoun_rewritten = resolve_pronouns(original, previous_person, source_lang)
        self._update_mentions(original)
        self._update_mentions(rewritten)
        applied: list[str] = []
        if pronoun_rewritten and self.memory.last_person is not None:
            applied.append(f"pronoun->{self.memory.last_person.source}")
        force = self._force_terms_in(rewritten)
        if force:
            applied.append(f"terms:{len(force)}")
        memory_hit = self._lookup_tm(original, target_lang) or self._lookup_tm(rewritten, target_lang)
        session_memory: tuple[tuple[str, str], ...] = ()
        if memory_hit:
            session_memory = (memory_hit,)
            applied.append("translation-memory")
        return PreparedUtterance(
            text=rewritten,
            original=original,
            context=context,
            force_terms=force,
            session_memory=session_memory,
            applied=tuple(applied),
            pronoun_rewritten=pronoun_rewritten,
        )

    def observe(self, original: str, rewritten: str, translated: str, target_lang: str) -> None:
        if not self.enabled:
            return
        target = (translated or "").strip()
        lang = (target_lang or "").strip().lower()
        for source in (original, rewritten):
            key = (source or "").strip()
            if key and target:
                self.memory.translations[(key, lang)] = target
        self._update_mentions(original)
        self._update_mentions(rewritten)

    def _lookup_tm(self, text: str, target_lang: str) -> tuple[str, str] | None:
        key = ((text or "").strip(), (target_lang or "").strip().lower())
        if not key[0]:
            return None
        hit = self.memory.translations.get(key) or self.memory.translations.get((key[0], ""))
        if hit:
            return (key[0], hit)
        folded = key[0].casefold()
        for (source, lang), target in self.memory.translations.items():
            if lang == key[1] and source.casefold() == folded:
                return (source, target)
        return None

    def _force_terms_in(self, text: str) -> tuple[tuple[str, str], ...]:
        if not text:
            return ()
        pairs: list[tuple[str, str]] = []
        selected: list[str] = []
        for bucket in (self.memory.characters, self.memory.places, self.memory.terms):
            for entry in sorted(bucket.values(), key=lambda item: len(item.source), reverse=True):
                source = entry.source
                if not source or source not in text or not entry.target:
                    continue
                if any(source in chosen or chosen in source for chosen in selected):
                    continue
                selected.append(source)
                pairs.append((source, entry.target))
        return tuple(pairs)

    def _update_mentions(self, text: str) -> None:
        blob = text or ""
        if not blob:
            return
        person = _longest_hit(blob, self.memory.characters)
        if person is not None:
            self.memory.last_person = person
        place = _longest_hit(blob, self.memory.places)
        if place is not None:
            self.memory.last_place = place

    def _seed(self, resources: TranslationResources | None, extra_entries: list[ResourceEntry]) -> None:
        for entry in extra_entries:
            self._add_entry(entry, default_kind="auto")
        if resources is None:
            return
        for entry in resources.merged("character_dictionary"):
            self._add_entry(entry, default_kind="person")
        for entry in resources.merged("glossary"):
            self._add_entry(entry, default_kind="term")
        for entry in resources.merged("translation_memory"):
            source = entry.source.strip()
            target = entry.target.strip()
            if source and target:
                self.memory.translations[(source, (entry.target_lang or "").strip().lower())] = target
                if not entry.target_lang:
                    self.memory.translations[(source, "")] = target

    def _add_entry(self, entry: ResourceEntry, default_kind: str) -> None:
        if not entry.source.strip():
            return
        if is_person_entry(entry) or default_kind == "person":
            self.memory.characters[entry.source] = entry
            return
        if is_place_entry(entry):
            self.memory.places[entry.source] = entry
            self.memory.terms[entry.source] = entry
            return
        self.memory.terms[entry.source] = entry


def _longest_hit(text: str, bucket: dict[str, ResourceEntry]) -> ResourceEntry | None:
    hit: ResourceEntry | None = None
    for entry in bucket.values():
        if entry.source and entry.source in text:
            if hit is None or len(entry.source) > len(hit.source):
                hit = entry
    return hit


def resolve_pronouns(text: str, person: ResourceEntry | None, source_lang: str) -> tuple[str, bool]:
    if not text or person is None or not person.source:
        return text, False
    if person.source in text:
        return text, False
    lang = (source_lang or "").strip().lower()
    gender = gender_of(person)
    name = person.source
    if lang in {"zh", "zh-cn", "zh-hans", "chinese"}:
        tokens = list(_ZH_FEMALE if gender in {"", "female"} else ()) + list(_ZH_MALE if gender in {"", "male"} else ())
        if gender == "":
            tokens = list(_ZH_FEMALE + _ZH_MALE)
        rewritten = text
        for token in tokens:
            rewritten = rewritten.replace(token, name)
        return rewritten, rewritten != text
    if lang in {"ja", "jp", "japanese"}:
        tokens = list(_JA_FEMALE if gender in {"", "female"} else ()) + list(_JA_MALE if gender in {"", "male"} else ())
        if gender == "":
            tokens = list(_JA_FEMALE + _JA_MALE)
        rewritten = text
        for token in sorted(tokens, key=len, reverse=True):
            rewritten = rewritten.replace(token, name)
        return rewritten, rewritten != text
    pronouns = []
    if gender in {"", "female"}:
        pronouns.extend(_EN_FEMALE)
    if gender in {"", "male"}:
        pronouns.extend(_EN_MALE)
    if not pronouns:
        return text, False
    pattern = re.compile(r"\b(" + "|".join(re.escape(item) for item in pronouns) + r")\b", re.IGNORECASE)

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token[:1].isupper():
            return name
        return name

    rewritten = pattern.sub(_replace, text)
    return rewritten, rewritten != text
