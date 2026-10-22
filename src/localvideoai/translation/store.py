"""Resolve local CTranslate2 translation model directories."""

from __future__ import annotations

from pathlib import Path

from localvideoai.core.exceptions import TranslationError
from localvideoai.core.paths import ensure_directory, model_search_roots, translation_models_dir
from localvideoai.models.state import is_disabled


def ctranslate2_model_path(root: Path) -> Path:
    nested = root / "model"
    if (nested / "model.bin").is_file():
        return nested
    if (root / "model.bin").is_file():
        return root
    raise TranslationError(f"翻译模型目录缺少 model.bin：{root}")


def tokenizer_kind(root: Path) -> str:
    if (root / "sentencepiece.model").is_file():
        return "shared_spm"
    if (root / "source.spm").is_file() and (root / "target.spm").is_file():
        return "dual_spm"
    if (root / "bpe.model").is_file():
        return "bpe"
    return "missing"


def is_translation_model_ready(root: Path) -> bool:
    try:
        ctranslate2_model_path(root)
    except TranslationError:
        return False
    return tokenizer_kind(root) in {"shared_spm", "dual_spm"}


def find_translation_model_dir(dir_name: str) -> Path | None:
    for root in model_search_roots():
        path = root / "translation" / dir_name
        if is_translation_model_ready(path):
            return path
    return None


def list_local_translation_models(*, include_disabled: bool = False) -> list[str]:
    names: set[str] = set()
    for root in model_search_roots():
        folder = root / "translation"
        if not folder.is_dir():
            continue
        for child in folder.iterdir():
            if child.is_dir() and is_translation_model_ready(child):
                names.add(child.name)
    result = sorted(names, key=str.lower)
    if include_disabled:
        return result
    return [name for name in result if not is_disabled(f"translation/{name}")]


def resolve_translation_model_dir(dir_name: str) -> Path:
    path = find_translation_model_dir(dir_name)
    if path is None:
        raise TranslationError(
            f"本地没有翻译模型 {dir_name}。请在 AI 模型中心导入或安装到 {translation_models_dir() / dir_name}"
        )
    if is_disabled(f"translation/{dir_name}"):
        raise TranslationError(f"翻译模型 {dir_name} 已禁用。请先在模型中心启用。")
    return path


def ensure_translation_models_dir() -> Path:
    return ensure_directory(translation_models_dir())
