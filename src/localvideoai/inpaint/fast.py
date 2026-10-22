"""Fast classical inpaint. Always available via OpenCV already pulled by RapidOCR."""

from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("硬字幕处理需要 OpenCV（随 RapidOCR 安装）") from exc


def inpaint_fast(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if mask.max() == 0:
        return rgb
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    filled = cv2.inpaint(bgr, mask, 4, cv2.INPAINT_TELEA)
    return cv2.cvtColor(filled, cv2.COLOR_BGR2RGB)


def temporal_fill(
    rgb: np.ndarray,
    mask: np.ndarray,
    previous: tuple[np.ndarray, np.ndarray] | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Copy uncovered pixels from the previous frame when the subtitle was absent."""
    if previous is None or mask.max() == 0:
        return rgb, mask
    prev_rgb, prev_mask = previous
    if prev_rgb.shape != rgb.shape:
        return rgb, mask
    borrow = (mask > 0) & (prev_mask == 0)
    if not borrow.any():
        return rgb, mask
    out = rgb.copy()
    out[borrow] = prev_rgb[borrow]
    remain = mask.copy()
    remain[borrow] = 0
    return out, remain
