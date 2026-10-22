"""Track subtitle boxes across time so neighboring frames share a stable mask."""

from __future__ import annotations

from localvideoai.inpaint.types import TimedRegion


def track_regions(regions: list[TimedRegion], *, pad: float = 0.02) -> list[TimedRegion]:
    if not regions:
        return []
    ordered = sorted(regions, key=lambda item: (item.start_ms, item.end_ms))
    tracks: list[TimedRegion] = [ordered[0]]
    for item in ordered[1:]:
        last = tracks[-1]
        if item.start_ms <= last.end_ms + 180 and _iou(last, item) >= 0.25:
            tracks[-1] = _union(last, item, pad)
        else:
            tracks.append(item)
    return [_padded(item, pad) for item in tracks]


def regions_at(tracks: list[TimedRegion], time_ms: int) -> list[TimedRegion]:
    return [item for item in tracks if item.start_ms <= time_ms <= item.end_ms]


def _iou(left: TimedRegion, right: TimedRegion) -> float:
    ax0, ay0, ax1, ay1 = left.x, left.y, left.x + left.w, left.y + left.h
    bx0, by0, bx1, by1 = right.x, right.y, right.x + right.w, right.y + right.h
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = left.w * left.h + right.w * right.h - inter
    return inter / union if union else 0.0


def _union(left: TimedRegion, right: TimedRegion, pad: float) -> TimedRegion:
    x0 = min(left.x, right.x)
    y0 = min(left.y, right.y)
    x1 = max(left.x + left.w, right.x + right.w)
    y1 = max(left.y + left.h, right.y + right.h)
    text = left.text if len(left.text) >= len(right.text) else right.text
    return TimedRegion(
        start_ms=min(left.start_ms, right.start_ms),
        end_ms=max(left.end_ms, right.end_ms),
        text=text,
        x=x0,
        y=y0,
        w=x1 - x0,
        h=y1 - y0,
        points=left.points + right.points,
    )


def _padded(item: TimedRegion, pad: float) -> TimedRegion:
    return TimedRegion(
        start_ms=item.start_ms,
        end_ms=item.end_ms,
        text=item.text,
        x=max(0.0, item.x - pad),
        y=max(0.0, item.y - pad),
        w=min(1.0 - max(0.0, item.x - pad), item.w + 2 * pad),
        h=min(1.0 - max(0.0, item.y - pad), item.h + 2 * pad),
        points=item.points,
    )
