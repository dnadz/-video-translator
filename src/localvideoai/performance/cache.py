"""Process-wide caches: media probes and loaded model runtimes."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


def media_cache_key(path: Path) -> tuple[str, int, int]:
    source = path.expanduser().resolve()
    stat = source.stat()
    return (str(source), int(stat.st_size), int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9))))


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    puts: int = 0
    evictions: int = 0

    def reset(self) -> None:
        self.hits = 0
        self.misses = 0
        self.puts = 0
        self.evictions = 0


class LruCache:
    def __init__(self, max_size: int = 16) -> None:
        self._max_size = max(1, int(max_size))
        self._items: OrderedDict[Any, Any] = OrderedDict()
        self._lock = Lock()
        self.stats = CacheStats()

    @property
    def max_size(self) -> int:
        return self._max_size

    def resize(self, max_size: int) -> None:
        with self._lock:
            self._max_size = max(1, int(max_size))
            self._evict_unlocked()

    def get(self, key: Any) -> Any | None:
        with self._lock:
            if key not in self._items:
                self.stats.misses += 1
                return None
            self._items.move_to_end(key)
            self.stats.hits += 1
            return self._items[key]

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                self._items[key] = value
                return
            self._items[key] = value
            self.stats.puts += 1
            self._evict_unlocked()

    def discard(self, key: Any) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self.stats.reset()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def _evict_unlocked(self) -> None:
        while len(self._items) > self._max_size:
            self._items.popitem(last=False)
            self.stats.evictions += 1


_MEDIA = LruCache(16)
_MODELS = LruCache(2)


def get_media_cache() -> LruCache:
    return _MEDIA


def get_model_cache() -> LruCache:
    return _MODELS


def reset_performance_caches() -> None:
    _MEDIA.clear()
    _MODELS.clear()


def configure_cache_limits(media_size: int, model_size: int) -> None:
    _MEDIA.resize(media_size)
    _MODELS.resize(model_size)
