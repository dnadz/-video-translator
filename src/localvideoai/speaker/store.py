"""Local speaker-embedding model files. Not packed into the EXE."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from localvideoai.core.paths import config_file, model_search_roots, speaker_models_dir
from localvideoai.models.state import is_disabled

CATALOG_NAME = "speaker_catalog.json"
MODEL_ID = "3dspeaker-eres2net-zh-16k"


def catalog_path() -> Path:
    return config_file(CATALOG_NAME)


def load_catalog() -> dict[str, Any]:
    path = catalog_path()
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def model_filename() -> str:
    model = load_catalog().get("model") or {}
    return str(model.get("filename") or "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")


def model_id() -> str:
    model = load_catalog().get("model") or {}
    return str(model.get("id") or MODEL_ID)


def model_urls() -> list[str]:
    model = load_catalog().get("model") or {}
    urls = model.get("urls") or []
    return [str(item) for item in urls if str(item).strip()]


def embedding_model_path() -> Path:
    found = find_embedding_model()
    return found if found is not None else speaker_models_dir() / model_filename()


def find_embedding_model() -> Path | None:
    name = model_filename()
    for root in model_search_roots():
        path = root / "speaker" / name
        if path.is_file() and path.stat().st_size > 1024:
            return path
    return None


def is_speaker_model_ready() -> bool:
    if is_disabled(f"speaker/{model_id()}"):
        return False
    return find_embedding_model() is not None


def list_local_speaker_models(*, include_disabled: bool = False) -> list[str]:
    if find_embedding_model() is None:
        return []
    ident = model_id()
    if include_disabled or not is_disabled(f"speaker/{ident}"):
        return [ident]
    return []
