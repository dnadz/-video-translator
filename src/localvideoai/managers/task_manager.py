from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from localvideoai.core.types import TaskSpec


class TaskManager(ABC):
    """Queue, persist, and resume local jobs. Must not fake progress."""

    @abstractmethod
    def enqueue(self, spec: TaskSpec) -> str:
        """Store a task. Execution is implemented in later phases."""

    @abstractmethod
    def get(self, task_id: str) -> dict[str, Any] | None:
        """Return a stored task or None."""

    @abstractmethod
    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        """List persisted tasks."""

    @abstractmethod
    def update(self, task_id: str, **fields: Any) -> dict[str, Any]:
        """Persist status and payload changes. Must not invent progress."""

    @abstractmethod
    def delete(self, task_id: str) -> None:
        """Remove a task from durable storage."""
