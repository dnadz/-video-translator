from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ProjectManager(ABC):
    """Persist local project files. Must not upload project data."""

    @abstractmethod
    def create(self, name: str, directory: Path) -> Path:
        """Create a new project folder and metadata file."""

    @abstractmethod
    def load(self, project_file: Path) -> dict[str, Any]:
        """Load project metadata from disk."""

    @abstractmethod
    def save(self, project_file: Path, data: dict[str, Any]) -> Path:
        """Write project metadata to disk."""
