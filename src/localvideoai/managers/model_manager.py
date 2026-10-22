from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

Progress = Callable[[int, int, str], None]


class ModelManager(ABC):
    """Download, verify, and switch local models. Models are not packed into the EXE."""

    @abstractmethod
    def list_local(self) -> list[str]:
        """List models already on disk."""

    @abstractmethod
    def resolve(self, model_id: str) -> Path:
        """Return the local path for a model id."""

    @abstractmethod
    def set_active(self, capability: str, model_id: str) -> None:
        """Bind a capability (speech, translation, ocr) to a local model."""

    @abstractmethod
    def list_records(self) -> list[Any]:
        """List catalog + disk records for the model center."""

    @abstractmethod
    def install(self, model_id: str, progress: Progress | None = None) -> Path:
        """Install a catalog model into the managed directory."""

    @abstractmethod
    def import_local(self, source: Path, model_id: str | None = None, progress: Progress | None = None) -> Path:
        """Import an already-deployed folder or file into the managed directory."""

    @abstractmethod
    def delete(self, model_id: str) -> None:
        """Delete a managed copy. Never deletes the software-tree deploy."""

    @abstractmethod
    def enable(self, model_id: str) -> None:
        """Allow engines to use this model."""

    @abstractmethod
    def disable(self, model_id: str) -> None:
        """Keep files on disk but stop engines from selecting this model."""

    @abstractmethod
    def set_models_root(self, path: Path) -> Path:
        """Change the independent writable model directory."""
