"""Drop redundant progress callbacks so the UI thread is not flooded."""

from __future__ import annotations

import time
from collections.abc import Callable

Progress = Callable[[int, int, str], None]


class ProgressThrottle:
    def __init__(self, interval_ms: int, emit: Progress) -> None:
        self.interval_ms = max(0, int(interval_ms))
        self._emit = emit
        self._last_ms = 0.0
        self.emitted = 0
        self.dropped = 0

    def __call__(self, current: int, total: int, message: str) -> None:
        now = time.monotonic() * 1000
        force = current >= total > 0 or current <= 0
        if not force and self.interval_ms and (now - self._last_ms) < self.interval_ms:
            self.dropped += 1
            return
        self._last_ms = now
        self.emitted += 1
        self._emit(current, total, message)
