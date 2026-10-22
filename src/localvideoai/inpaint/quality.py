"""Judge whether inpaint is safe. Unreliable repair must recommend overlay."""

from __future__ import annotations

import numpy as np

from localvideoai.inpaint.types import MODE_OVERLAY, MODE_SMART

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

PERSON_RISK_LIMIT = 0.22
RESIDUAL_EDGE_LIMIT = 18.0
FACE_CHANGE_LIMIT = 28.0


def person_risk(rgb: np.ndarray, mask: np.ndarray) -> float:
    if mask.max() == 0:
        return 0.0
    skin = _skin_mask(rgb)
    overlap = np.logical_and(mask > 0, skin > 0)
    return float(overlap.sum()) / float((mask > 0).sum())


def residual_edge_score(original: np.ndarray, repaired: np.ndarray, mask: np.ndarray) -> float:
    if cv2 is None or mask.max() == 0:
        return 0.0
    gray = cv2.cvtColor(repaired, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    return float(edges[mask > 0].mean()) if (mask > 0).any() else 0.0


def face_change_score(original: np.ndarray, repaired: np.ndarray, mask: np.ndarray) -> float:
    skin = _skin_mask(original)
    watch = np.logical_and(mask > 0, skin > 0)
    if not watch.any():
        return 0.0
    diff = np.abs(original.astype(np.int16) - repaired.astype(np.int16)).mean(axis=2)
    return float(diff[watch].mean())


def decide_mode(
    *,
    requested: str,
    risk: float,
    residual: float,
    face_change: float,
    residual_text: bool,
) -> tuple[str, str, str, float]:
    """Return (used_mode, recommended_mode, reason, quality_score)."""
    penalties = risk * 80 + min(residual, 40.0) + min(face_change, 40.0) + (25.0 if residual_text else 0.0)
    score = max(0.0, min(100.0, 100.0 - penalties))
    unreliable = (
        requested == MODE_SMART
        and (
            risk >= PERSON_RISK_LIMIT
            or residual >= RESIDUAL_EDGE_LIMIT
            or face_change >= FACE_CHANGE_LIMIT
            or residual_text
        )
    )
    if requested != MODE_SMART:
        return requested, requested, "", score
    if unreliable:
        reasons = []
        if risk >= PERSON_RISK_LIMIT:
            reasons.append("字幕压在人物/肤色区域上，去除会破坏人物")
        if residual_text or residual >= RESIDUAL_EDGE_LIMIT:
            reasons.append("修复后仍可能残留字幕边缘")
        if face_change >= FACE_CHANGE_LIMIT:
            reasons.append("人物区域变化过大")
        reason = "修复质量不可靠，自动建议覆盖模式。" + "；".join(reasons)
        return MODE_OVERLAY, MODE_OVERLAY, reason, score
    return MODE_SMART, MODE_SMART, "智能去除可用", score


def _skin_mask(rgb: np.ndarray) -> np.ndarray:
    if cv2 is None:
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        return ((r > 90) & (g > 40) & (b > 20) & (r > g) & (r > b)).astype(np.uint8) * 255
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    lower = cv2.inRange(hsv, (0, 40, 50), (25, 180, 255))
    upper = cv2.inRange(hsv, (160, 40, 50), (180, 180, 255))
    orange = cv2.inRange(hsv, (8, 60, 60), (28, 200, 255))
    return cv2.bitwise_or(cv2.bitwise_or(lower, upper), orange)
