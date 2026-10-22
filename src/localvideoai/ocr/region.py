"""Normalized subtitle regions and auto-detection from OCR boxes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedRegion:
    x: float
    y: float
    w: float
    h: float

    def clamp(self) -> "NormalizedRegion":
        x = min(max(self.x, 0.0), 0.98)
        y = min(max(self.y, 0.0), 0.98)
        w = min(max(self.w, 0.02), 1.0 - x)
        h = min(max(self.h, 0.02), 1.0 - y)
        return NormalizedRegion(x, y, w, h)

    def as_tuple(self) -> tuple[float, float, float, float]:
        item = self.clamp()
        return (round(item.x, 4), round(item.y, 4), round(item.w, 4), round(item.h, 4))

    def pixel_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        item = self.clamp()
        x0 = max(0, int(item.x * width))
        y0 = max(0, int(item.y * height))
        x1 = min(width, int((item.x + item.w) * width))
        y1 = min(height, int((item.y + item.h) * height))
        if x1 <= x0:
            x1 = min(width, x0 + 1)
        if y1 <= y0:
            y1 = min(height, y0 + 1)
        return x0, y0, x1, y1


DEFAULT_BOTTOM = NormalizedRegion(0.04, 0.70, 0.92, 0.28)
PROBE_LOWER = NormalizedRegion(0.0, 0.50, 1.0, 0.50)


def region_from_boxes(
    boxes: list[tuple[float, float, float, float]],
    *,
    pad: float = 0.04,
    fallback: NormalizedRegion = DEFAULT_BOTTOM,
) -> NormalizedRegion:
    """boxes are normalized (x0, y0, x1, y1). Keep the lower-frame subtitle band."""
    lower = [box for box in boxes if box[1] >= 0.45 or box[3] >= 0.55]
    chosen = lower or boxes
    if not chosen:
        return fallback.clamp()
    x0 = min(item[0] for item in chosen)
    y0 = min(item[1] for item in chosen)
    x1 = max(item[2] for item in chosen)
    y1 = max(item[3] for item in chosen)
    return NormalizedRegion(x0 - pad, y0 - pad, (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad).clamp()


def union_norm_box(points: tuple[tuple[float, float], ...]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))
