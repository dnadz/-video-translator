"""Resolve RapidOCR ONNX files from the managed directory, then deployed copies."""

from __future__ import annotations

import shutil
from pathlib import Path

from localvideoai.core.exceptions import OCRError
from localvideoai.core.paths import ensure_directory, model_search_roots, ocr_models_dir
from localvideoai.models.state import is_disabled

DET_NAME = "PP-OCRv6_det_small.onnx"
REC_NAME = "PP-OCRv6_rec_small.onnx"
CLS_NAME = "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
MODEL_ID = "ppocrv6-small"


def ocr_files_present(root: Path) -> bool:
    return all((root / name).is_file() for name in (DET_NAME, REC_NAME, CLS_NAME))


def find_ocr_root() -> Path | None:
    for root in model_search_roots():
        path = root / "ocr"
        if ocr_files_present(path):
            return path
    return None


def is_ocr_ready() -> bool:
    if is_disabled(f"ocr/{MODEL_ID}"):
        return False
    return find_ocr_root() is not None


def resolve_ocr_models() -> dict[str, Path]:
    root = find_ocr_root()
    if root is None:
        root = ocr_models_dir()
        missing = [str(root / name) for name in (DET_NAME, REC_NAME, CLS_NAME) if not (root / name).is_file()]
        raise OCRError(
            "本地没有 OCR 模型。请在 AI 模型中心导入或安装到 "
            f"{root}（缺少：{', '.join(missing)}）"
        )
    if is_disabled(f"ocr/{MODEL_ID}"):
        raise OCRError("OCR 模型已禁用。请先在模型中心启用。")
    return {"det": root / DET_NAME, "rec": root / REC_NAME, "cls": root / CLS_NAME}


def copy_bundled_models(source_dir: Path | None = None) -> Path:
    destination = ensure_directory(ocr_models_dir())
    source = source_dir or _bundled_rapidocr_models()
    if source is None:
        raise OCRError("未找到 RapidOCR 自带模型目录，请安装 rapidocr>=3.9")
    for name in (DET_NAME, REC_NAME, CLS_NAME):
        src = source / name
        if not src.is_file():
            raise OCRError(f"RapidOCR 包内缺少 {name}：{src}")
        shutil.copy2(src, destination / name)
    if not ocr_files_present(destination):
        raise OCRError(f"OCR 模型复制不完整：{destination}")
    return destination


def _bundled_rapidocr_models() -> Path | None:
    try:
        import rapidocr
    except ImportError:
        return None
    path = Path(rapidocr.__file__).resolve().parent / "models"
    if path.is_dir():
        return path
    return None
