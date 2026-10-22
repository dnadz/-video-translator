"""Resolve faster-whisper models from the managed directory, then deployed copies."""

from __future__ import annotations

from pathlib import Path

from localvideoai.core.exceptions import SpeechError
from localvideoai.core.paths import ensure_directory, model_search_roots, speech_models_dir
from localvideoai.models.state import is_disabled

KNOWN_MODELS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    # Official Systran turbo repo 401s from this network; public CT2 conversion.
    "large-v3-turbo": "deepdml/faster-whisper-large-v3-turbo-ct2",
}


def model_dir(model_id: str) -> Path:
    return speech_models_dir() / model_id


def _speech_ready(path: Path) -> bool:
    return (path / "model.bin").is_file() and (path / "config.json").is_file()


def find_model_dir(model_id: str, roots: list[Path] | None = None) -> Path | None:
    search = roots if roots is not None else model_search_roots()
    for root in search:
        candidate = root / model_id if root.name == "speech" else root / "speech" / model_id
        if _speech_ready(candidate):
            return candidate
    return None


def is_model_present(model_id: str, roots: list[Path] | None = None) -> bool:
    return find_model_dir(model_id, roots=roots) is not None


def is_model_ready(model_id: str) -> bool:
    if is_disabled(f"speech/{model_id}"):
        return False
    return is_model_present(model_id)


def list_local_models(*, include_disabled: bool = False) -> list[str]:
    names: set[str] = set()
    for root in model_search_roots():
        folder = root / "speech"
        if not folder.is_dir():
            continue
        for child in folder.iterdir():
            if child.is_dir() and _speech_ready(child):
                names.add(child.name)
    result = sorted(names)
    if include_disabled:
        return result
    return [name for name in result if not is_disabled(f"speech/{name}")]


def resolve_model_path(model_id: str) -> Path:
    path = find_model_dir(model_id)
    if path is None:
        raise SpeechError(
            f"本地没有语音模型 {model_id}。请在 AI 模型中心导入或安装到 {model_dir(model_id)}"
        )
    if is_disabled(f"speech/{model_id}"):
        raise SpeechError(f"语音模型 {model_id} 已禁用。请先在模型中心启用。")
    return path


def download_model(model_id: str, repo_id: str | None = None) -> Path:
    """Download a CTranslate2 Whisper model. Caller must allow network for this step only."""
    if model_id not in KNOWN_MODELS and not repo_id:
        raise SpeechError(f"未知语音模型：{model_id}")
    destination = ensure_directory(model_dir(model_id))
    repo = repo_id or KNOWN_MODELS[model_id]
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SpeechError("缺少 huggingface_hub，无法下载模型。请安装 faster-whisper。") from exc
    import os

    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    # Public Systran weights; a stale/invalid HF token makes huggingface.co return 401.
    saved_tokens = {
        key: os.environ.pop(key)
        for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
        if key in os.environ
    }

    last_error: Exception | None = None
    endpoints = ["https://huggingface.co", "https://hf-mirror.com"]
    current = os.environ.get("HF_ENDPOINT")
    if current and current not in endpoints:
        endpoints.insert(0, current)
    seen: set[str] = set()
    try:
        for endpoint in endpoints:
            if endpoint in seen:
                continue
            seen.add(endpoint)
            os.environ["HF_ENDPOINT"] = endpoint
            try:
                snapshot_download(repo_id=repo, local_dir=str(destination), max_workers=4, token=False)
                break
            except Exception as exc:
                last_error = exc
                continue
        else:
            raise SpeechError(f"下载语音模型失败：{repo}  {last_error}") from last_error
    finally:
        os.environ.update(saved_tokens)
    if not _speech_ready(destination):
        raise SpeechError(f"模型下载不完整：{destination}")
    return destination
