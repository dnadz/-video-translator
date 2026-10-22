"""Resolve the optional local LaMa ONNX. Missing model is a real fallback, not a fake AI."""

from __future__ import annotations

from pathlib import Path

from localvideoai.core.paths import ensure_directory, inpaint_models_dir, model_search_roots
from localvideoai.models.state import is_disabled

MODEL_FILENAME = "lama_fp32.onnx"
MODEL_ID = "carve-lama-onnx-fp32"
MIN_BYTES = 50_000_000
MODEL_URLS = (
    "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx",
    "https://hf-mirror.com/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx",
)


def find_lama_model() -> Path | None:
    for root in model_search_roots():
        path = root / "inpaint" / MODEL_FILENAME
        if path.is_file() and path.stat().st_size >= MIN_BYTES:
            return path
    return None


def lama_model_path() -> Path:
    found = find_lama_model()
    return found if found is not None else inpaint_models_dir() / MODEL_FILENAME


def is_lama_ready() -> bool:
    if is_disabled(f"inpaint/{MODEL_ID}"):
        return False
    return find_lama_model() is not None


def require_model_dir() -> Path:
    return ensure_directory(inpaint_models_dir())
