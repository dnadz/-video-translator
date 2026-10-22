"""Persist enable/disable and last-active model choices in user data."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import ModelError
from localvideoai.core.paths import ensure_directory, user_data_dir

STATE_NAME = "models_state.json"


def state_path() -> Path:
    return user_data_dir() / STATE_NAME


def default_state() -> dict[str, Any]:
    return {"disabled": [], "active": {}}


def load_model_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return default_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelError(f"无法读取模型状态：{path}") from exc
    if not isinstance(payload, dict):
        raise ModelError(f"模型状态格式错误：{path}")
    disabled = payload.get("disabled") or []
    active = payload.get("active") or {}
    if not isinstance(disabled, list) or not isinstance(active, dict):
        raise ModelError(f"模型状态字段无效：{path}")
    return {
        "disabled": [str(item) for item in disabled],
        "active": {str(key): str(value) for key, value in active.items()},
    }


def save_model_state(state: dict[str, Any]) -> Path:
    path = state_path()
    ensure_directory(path.parent)
    payload = {
        "disabled": list(dict.fromkeys(str(item) for item in (state.get("disabled") or []))),
        "active": {str(key): str(value) for key, value in (state.get("active") or {}).items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def is_disabled(model_id: str) -> bool:
    return model_id in set(load_model_state()["disabled"])


def disable_model(model_id: str) -> dict[str, Any]:
    state = load_model_state()
    if model_id not in state["disabled"]:
        state["disabled"].append(model_id)
    save_model_state(state)
    return deepcopy(state)


def enable_model(model_id: str) -> dict[str, Any]:
    state = load_model_state()
    state["disabled"] = [item for item in state["disabled"] if item != model_id]
    save_model_state(state)
    return deepcopy(state)


def set_active_model(capability: str, model_id: str) -> dict[str, Any]:
    state = load_model_state()
    state["active"][capability] = model_id
    if model_id in state["disabled"]:
        state["disabled"] = [item for item in state["disabled"] if item != model_id]
    save_model_state(state)
    return deepcopy(state)
