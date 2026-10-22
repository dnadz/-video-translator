"""Cover the original hard subtitle with a bar and burn replacement text."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from localvideoai.inpaint.types import TimedRegion


def cover_and_burn(rgb: np.ndarray, regions: list[TimedRegion], mask: np.ndarray) -> np.ndarray:
    out = rgb.copy()
    if mask.max() > 0:
        ys, xs = np.where(mask > 0)
        y0, y1 = max(0, ys.min() - 6), min(out.shape[0], ys.max() + 7)
        x0, x1 = max(0, xs.min() - 8), min(out.shape[1], xs.max() + 9)
        bar = out[y0:y1, x0:x1]
        if bar.size:
            color = np.median(bar.reshape(-1, 3), axis=0).astype(np.uint8)
            # Darken so new text stays readable.
            color = (color.astype(np.int16) * 0.25).astype(np.uint8)
            out[y0:y1, x0:x1] = color
    if not regions:
        return out
    text = regions[0].text
    return _draw_text(out, text)


def _draw_text(rgb: np.ndarray, text: str) -> np.ndarray:
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)
    font = _font(max(28, rgb.shape[0] // 22))
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = max(8, (rgb.shape[1] - width) // 2)
    y = max(8, rgb.shape[0] - height - max(28, rgb.shape[0] // 18))
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=(255, 255, 255))
    return np.asarray(image)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    for name in ("msyh.ttc", "msyh.ttf", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"):
        path = root / name
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()
