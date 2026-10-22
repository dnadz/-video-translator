"""Write a real side-by-side comparison still of original vs processed."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from localvideoai.core.paths import ensure_directory, logs_dir
from localvideoai.ocr.sampler import extract_still


def write_comparison(
    original: Path,
    processed: Path,
    destination: Path | None = None,
    *,
    time_ms: int = 1200,
    label: str = "",
) -> Path:
    dest = destination or (logs_dir() / "phase14_compare" / f"{original.stem}_{processed.stem}.jpg")
    ensure_directory(dest.parent)
    left_path = dest.with_name(dest.stem + "_left.jpg")
    right_path = dest.with_name(dest.stem + "_right.jpg")
    extract_still(original, left_path, time_ms=time_ms)
    extract_still(processed, right_path, time_ms=time_ms)
    left = Image.open(left_path).convert("RGB")
    right = Image.open(right_path).convert("RGB")
    height = min(left.height, right.height, 360)
    left = left.resize((int(left.width * height / left.height), height))
    right = right.resize((int(right.width * height / right.height), height))
    canvas = Image.new("RGB", (left.width + right.width + 24, height + 36), (18, 18, 22))
    canvas.paste(left, (8, 28))
    canvas.paste(right, (left.width + 16, 28))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((8, 6), f"原视频 {original.name}", fill=(220, 220, 220), font=font)
    draw.text((left.width + 16, 6), f"处理后 {processed.name} {label}", fill=(220, 220, 220), font=font)
    canvas.save(dest, quality=90)
    return dest


def region_delta(original_rgb: np.ndarray, processed_rgb: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    if original_rgb.shape != processed_rgb.shape:
        return 0.0, 0.0
    diff = np.abs(original_rgb.astype(np.int16) - processed_rgb.astype(np.int16)).mean(axis=2)
    inside = float(diff[mask > 0].mean()) if (mask > 0).any() else 0.0
    outside = float(diff[mask == 0].mean()) if (mask == 0).any() else 0.0
    return inside, outside
