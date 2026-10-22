"""Build a tight per-frame subtitle mask. Prefer OCR polygons over the whole band."""

from __future__ import annotations

import numpy as np

from localvideoai.inpaint.types import TimedRegion

try:
    import cv2
except ImportError:  # pragma: no cover - RapidOCR already depends on OpenCV
    cv2 = None


def mask_for_frame(
    height: int,
    width: int,
    regions: list[TimedRegion],
    *,
    dilate_px: int = 10,
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    if not regions:
        return mask
    for region in regions:
        if region.points and len(region.points) >= 3:
            pts = np.array(
                [[int(px * width), int(py * height)] for px, py in region.points],
                dtype=np.int32,
            )
            if cv2 is not None:
                cv2.fillConvexPoly(mask, pts, 255)
            else:
                _fill_box(mask, region, width, height)
        else:
            _fill_box(mask, region, width, height)
    if cv2 is not None and dilate_px > 0 and int(mask.max()) > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px, dilate_px))
        mask = cv2.dilate(mask, kernel)
    return mask


def _fill_box(mask: np.ndarray, region: TimedRegion, width: int, height: int) -> None:
    x0 = max(0, int(region.x * width))
    y0 = max(0, int(region.y * height))
    x1 = min(width, int((region.x + region.w) * width))
    y1 = min(height, int((region.y + region.h) * height))
    if x1 > x0 and y1 > y0:
        mask[y0:y1, x0:x1] = 255
