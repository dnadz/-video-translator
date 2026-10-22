"""Copy RapidOCR ONNX models into models/ocr/. Offline if rapidocr is already installed."""

from __future__ import annotations

from localvideoai.core.paths import ocr_models_dir
from localvideoai.ocr.store import copy_bundled_models, is_ocr_ready


def main() -> int:
    print(f"model root: {ocr_models_dir()}")
    if is_ocr_ready():
        print("already present: PP-OCRv6 small det/rec/cls")
        return 0
    path = copy_bundled_models()
    print(f"copied RapidOCR models to {path}")
    if not is_ocr_ready():
        raise SystemExit("OCR models missing after copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
