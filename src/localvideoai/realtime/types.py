"""Realtime preview results. No model SDKs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RealtimeCue:
    start_ms: int
    end_ms: int
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    window_ms: int
    process_ms: int
    requested_ms: int
    profile: str
    speech_device: str
    model_id: str

    def display_text(self) -> str:
        translated = (self.translated_text or "").strip()
        source = (self.source_text or "").strip()
        if translated and source and translated != source:
            return f"{source}\n{translated}"
        return translated or source
