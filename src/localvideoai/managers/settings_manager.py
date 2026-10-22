from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import ConfigurationError
from localvideoai.core.paths import default_config_path, ensure_directory, user_config_path


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read config file: {path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in config file: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"Config root must be an object: {path}")
    return data


class SettingsManager:
    """Load shipped defaults and persist user settings as JSON."""

    def __init__(
        self,
        *,
        defaults_path: Path | None = None,
        user_path: Path | None = None,
    ) -> None:
        self.defaults_path = defaults_path or default_config_path()
        self.user_path = user_path or user_config_path()
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.defaults_path.is_file():
            raise ConfigurationError(f"Default config is missing: {self.defaults_path}")
        data = _read_json(self.defaults_path)
        if self.user_path.is_file():
            data = _deep_merge(data, _read_json(self.user_path))
        self._data = data
        return deepcopy(self._data)

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self._data)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        current: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return deepcopy(current)

    def set(self, dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        if not parts or any(not p for p in parts):
            raise ConfigurationError(f"Invalid settings key: {dotted_key}")
        cursor = self._data
        for part in parts[:-1]:
            existing = cursor.get(part)
            if not isinstance(existing, dict):
                cursor[part] = {}
            cursor = cursor[part]
        cursor[parts[-1]] = deepcopy(value)

    def save(self) -> Path:
        if self.get("privacy.upload_media") is True:
            raise ConfigurationError("upload_media must remain false; remote upload is not allowed by default.")
        target = self.user_path
        ensure_directory(target.parent)
        payload = json.dumps(self._data, ensure_ascii=False, indent=2) + "\n"
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(target)
        except OSError as exc:
            raise ConfigurationError(f"Cannot save config file: {target}") from exc
        return target
