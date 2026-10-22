"""Install / import / delete against the managed model root only."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from localvideoai.core.exceptions import ModelError
from localvideoai.core.paths import (
    bundled_models_dir,
    ensure_directory,
    inpaint_models_dir,
    managed_models_dir,
    ocr_models_dir,
    speaker_models_dir,
    speech_models_dir,
    translation_models_dir,
)
from localvideoai.models.catalog import CatalogEntry, catalog_by_id
from localvideoai.ocr import store as ocr_store
from localvideoai.speaker import store as speaker_store
from localvideoai.speech import store as speech_store
from localvideoai.translation import store as translation_store

Progress = Callable[[int, int, str], None]
IGNORE_COPY_PARTS = {".cache", ".git"}


def normalize_model_id(model_id: str) -> str:
    text = model_id.strip().replace("\\", "/")
    if "/" not in text:
        if text in speech_store.KNOWN_MODELS:
            return f"speech/{text}"
        if text == ocr_store.MODEL_ID:
            return f"ocr/{text}"
        if text == speaker_store.model_id():
            return f"speaker/{text}"
        return f"speech/{text}"
    return text


def capability_of(model_id: str) -> str:
    return normalize_model_id(model_id).split("/", 1)[0]


def managed_destination(model_id: str) -> Path:
    full = normalize_model_id(model_id)
    capability, local_id = full.split("/", 1)
    if capability == "speech":
        return speech_models_dir() / local_id
    if capability == "ocr":
        return ocr_models_dir()
    if capability == "translation":
        return translation_models_dir() / local_id
    if capability == "speaker":
        return speaker_models_dir()
    if capability == "inpaint":
        return inpaint_models_dir()
    raise ModelError(f"未知模型类型：{model_id}")


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        if IGNORE_COPY_PARTS.intersection(child.relative_to(path).parts):
            continue
        try:
            total += child.stat().st_size
        except OSError:
            continue
    return total


def copy_tree(source: Path, destination: Path, progress: Progress | None = None) -> Path:
    if not source.exists():
        raise ModelError(f"导入源不存在：{source}")
    if source.is_file():
        ensure_directory(destination if destination.suffix == "" else destination.parent)
        target = destination if destination.suffix else destination / source.name
        shutil.copy2(source, target)
        if progress:
            progress(1, 1, f"已复制 {source.name}")
        return target
    files = [
        child
        for child in source.rglob("*")
        if child.is_file() and not IGNORE_COPY_PARTS.intersection(child.relative_to(source).parts)
    ]
    total = max(1, len(files))
    ensure_directory(destination)
    for index, file in enumerate(files, start=1):
        rel = file.relative_to(source)
        target = destination / rel
        ensure_directory(target.parent)
        shutil.copy2(file, target)
        if progress:
            progress(index, total, f"正在复制 {rel}")
    return destination


def detect_import(source: Path) -> str:
    path = source
    if path.is_file():
        name = path.name.lower()
        if name == "lama_fp32.onnx":
            return "inpaint/carve-lama-onnx-fp32"
        if name.endswith(".onnx") and "3dspeaker" in name:
            return f"speaker/{speaker_store.model_id()}"
        raise ModelError(f"无法识别该文件：{path}")
    if (path / "model.bin").is_file() and (path / "config.json").is_file():
        return f"speech/{path.name}"
    if translation_store.is_translation_model_ready(path):
        return f"translation/{path.name}"
    if all((path / name).is_file() for name in (ocr_store.DET_NAME, ocr_store.REC_NAME, ocr_store.CLS_NAME)):
        return f"ocr/{ocr_store.MODEL_ID}"
    onnx_files = list(path.glob("*.onnx"))
    if any(item.name == "lama_fp32.onnx" for item in onnx_files):
        return "inpaint/carve-lama-onnx-fp32"
    speaker_name = speaker_store.model_filename()
    if any(item.name == speaker_name for item in onnx_files):
        return f"speaker/{speaker_store.model_id()}"
    raise ModelError(f"无法识别模型目录：{path}。需要 Whisper（model.bin+config.json）、OCR ONNX、翻译包或说话人/修复 ONNX。")


def bundled_source(entry: CatalogEntry) -> Path | None:
    root = bundled_models_dir()
    if entry.capability == "speech":
        path = root / "speech" / entry.local_id
        return path if speech_store.is_model_present(entry.local_id, roots=[root]) else None
    if entry.capability == "ocr":
        path = root / "ocr"
        return path if ocr_store.ocr_files_present(path) else None
    if entry.capability == "translation":
        path = root / "translation" / entry.local_id
        return path if translation_store.is_translation_model_ready(path) else None
    if entry.capability == "speaker":
        path = root / "speaker" / speaker_store.model_filename()
        return path if path.is_file() and path.stat().st_size > 1024 else None
    if entry.capability == "inpaint":
        from localvideoai.inpaint.store import MIN_BYTES, MODEL_FILENAME

        path = root / "inpaint" / MODEL_FILENAME
        return path if path.is_file() and path.stat().st_size >= MIN_BYTES else None
    return None


def import_local(source: Path, model_id: str | None = None, progress: Progress | None = None) -> Path:
    resolved = Path(source).expanduser().resolve()
    full_id = normalize_model_id(model_id) if model_id else detect_import(resolved)
    dest = managed_destination(full_id)
    if dest.exists() and dest.resolve() == resolved:
        return dest
    if is_under(resolved, dest if dest.is_dir() else dest.parent) and dest.exists() and dest.resolve() == resolved:
        return dest
    capability = capability_of(full_id)
    if capability == "speaker" and resolved.is_file():
        ensure_directory(dest)
        target = dest / speaker_store.model_filename()
        shutil.copy2(resolved, target)
        if progress:
            progress(1, 1, f"已导入 {target.name}")
        return target
    if capability == "inpaint" and resolved.is_file():
        from localvideoai.inpaint.store import MODEL_FILENAME

        ensure_directory(dest)
        target = dest / MODEL_FILENAME
        shutil.copy2(resolved, target)
        if progress:
            progress(1, 1, f"已导入 {target.name}")
        return target
    if dest.exists() and dest.resolve() == bundled_models_dir().resolve():
        raise ModelError("不能把软件目录当作导入目标。")
    copied = copy_tree(resolved, dest, progress)
    _assert_ready(full_id)
    return copied


def install(model_id: str, progress: Progress | None = None) -> Path:
    full_id = normalize_model_id(model_id)
    catalog = catalog_by_id()
    entry = catalog.get(full_id)
    if entry is None:
        raise ModelError(f"模型目录里没有 {full_id}")
    source = bundled_source(entry)
    if source is not None:
        if progress:
            progress(0, 1, f"从已部署目录导入 {entry.name}")
        return import_local(source, full_id, progress)
    if entry.capability == "speech":
        if progress:
            progress(0, 1, f"正在下载语音模型 {entry.local_id}")
        path = speech_store.download_model(entry.local_id, repo_id=entry.repo or None)
        if progress:
            progress(1, 1, f"已安装 {entry.name}")
        return path
    if entry.capability == "ocr":
        if progress:
            progress(0, 1, "正在从 RapidOCR 包复制 OCR 模型")
        path = ocr_store.copy_bundled_models()
        if progress:
            progress(1, 1, "已安装 OCR 模型")
        return path
    raise ModelError(
        f"本地没有可导入的 {entry.name}，且该类型不会在模型中心自动下载大文件。"
        "请选择已部署目录导入。"
    )


def delete_managed(model_id: str) -> None:
    full_id = normalize_model_id(model_id)
    dest = managed_destination(full_id)
    managed = managed_models_dir()
    if not dest.exists():
        raise ModelError(f"管理目录里没有可删除的副本：{full_id}")
    if not is_under(dest, managed):
        raise ModelError("只能删除独立模型目录中的副本，不能删除软件目录里的已部署模型。")
    capability = capability_of(full_id)
    if capability in {"ocr", "speaker", "inpaint"}:
        _delete_typed_files(full_id, dest)
        return
    if dest.is_dir():
        shutil.rmtree(dest)
        return
    dest.unlink()


def _delete_typed_files(model_id: str, dest: Path) -> None:
    capability = capability_of(model_id)
    if capability == "ocr":
        for name in (ocr_store.DET_NAME, ocr_store.REC_NAME, ocr_store.CLS_NAME):
            path = dest / name
            if path.is_file():
                path.unlink()
        return
    if capability == "speaker":
        path = dest / speaker_store.model_filename()
        if path.is_file():
            path.unlink()
        return
    if capability == "inpaint":
        from localvideoai.inpaint.store import MODEL_FILENAME

        path = dest / MODEL_FILENAME
        if path.is_file():
            path.unlink()


def _assert_ready(model_id: str) -> None:
    full_id = normalize_model_id(model_id)
    capability, local_id = full_id.split("/", 1)
    if capability == "speech" and not speech_store.is_model_present(local_id):
        raise ModelError(f"导入后语音模型不完整：{full_id}")
    if capability == "ocr" and not ocr_store.ocr_files_present(ocr_models_dir()):
        raise ModelError("导入后 OCR 模型不完整")
    if capability == "translation" and translation_store.find_translation_model_dir(local_id) is None:
        raise ModelError(f"导入后翻译模型不完整：{full_id}")
