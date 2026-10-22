"""Bidirectional temporal fill for hard-sub removal. Not a generative video model."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("硬字幕处理需要 OpenCV（随 RapidOCR 安装）") from exc

Neighbor = tuple[np.ndarray, np.ndarray]
TEMPORAL_RADIUS = 6
_FLOW_NEIGHBORS = 2


def temporal_inpaint(
    rgb: np.ndarray,
    mask: np.ndarray,
    past: Sequence[Neighbor] = (),
    future: Sequence[Neighbor] = (),
    *,
    use_flow: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Fill masked pixels from nearby frames where the subtitle was absent.

    ``past`` is oldest-first. ``future`` is nearest-first. Remaining holes stay
    in the returned mask for LaMa / TELEA.
    """
    if mask.max() == 0:
        return rgb, mask
    ordered = _nearest_first(past, future)
    if not ordered:
        return rgb, mask
    filled = rgb.copy()
    remain = mask.copy()
    for index, (src_rgb, src_mask) in enumerate(ordered):
        if src_rgb.shape != rgb.shape or src_mask.shape != mask.shape:
            continue
        borrow = (remain > 0) & (src_mask == 0)
        if borrow.any():
            filled[borrow] = src_rgb[borrow]
            remain[borrow] = 0
        if remain.max() == 0:
            return filled, remain
        if use_flow and index < _FLOW_NEIGHBORS:
            filled, remain = _flow_fill(filled, remain, src_rgb, src_mask)
            if remain.max() == 0:
                return filled, remain
    return filled, remain


def _nearest_first(past: Sequence[Neighbor], future: Sequence[Neighbor]) -> list[Neighbor]:
    ordered: list[Neighbor] = []
    span = max(len(past), len(future))
    for offset in range(span):
        if offset < len(future):
            ordered.append(future[offset])
        if offset < len(past):
            ordered.append(past[-(offset + 1)])
    return ordered


def _flow_fill(
    dst_rgb: np.ndarray,
    dst_mask: np.ndarray,
    src_rgb: np.ndarray,
    src_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if dst_mask.max() == 0:
        return dst_rgb, dst_mask
    gray_d = cv2.cvtColor(dst_rgb, cv2.COLOR_RGB2GRAY)
    gray_s = cv2.cvtColor(src_rgb, cv2.COLOR_RGB2GRAY)
    flow = cv2.calcOpticalFlowFarneback(gray_d, gray_s, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    height, width = dst_mask.shape
    ys, xs = np.where(dst_mask > 0)
    if ys.size == 0:
        return dst_rgb, dst_mask
    sample_x = np.clip(np.rint(xs + flow[ys, xs, 0]).astype(np.int32), 0, width - 1)
    sample_y = np.clip(np.rint(ys + flow[ys, xs, 1]).astype(np.int32), 0, height - 1)
    ok = src_mask[sample_y, sample_x] == 0
    if not ok.any():
        return dst_rgb, dst_mask
    out = dst_rgb.copy()
    remain = dst_mask.copy()
    out[ys[ok], xs[ok]] = src_rgb[sample_y[ok], sample_x[ok]]
    remain[ys[ok], xs[ok]] = 0
    return out, remain
