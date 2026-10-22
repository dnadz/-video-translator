from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class PresetManager(ABC):
    """Load export and translation presets from local JSON files."""

    @abstractmethod
    def list_presets(self) -> list[str]:
        """Return preset identifiers."""

    @abstractmethod
    def load(self, preset_id: str) -> dict[str, Any]:
        """Load a preset from disk."""

    @abstractmethod
    def save(self, preset_id: str, data: dict[str, Any], path: Path | None = None) -> Path:
        """Write a preset to disk."""
