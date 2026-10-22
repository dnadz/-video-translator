from abc import ABC, abstractmethod


class BaseEngine(ABC):
    """All processing engines are replaceable. UI must not instantiate model SDKs."""

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Stable identifier used by ModelManager / TaskManager."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for logs and UI."""
