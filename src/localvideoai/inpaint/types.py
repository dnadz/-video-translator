"""Hard-subtitle processing modes and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MODE_KEEP = "keep"
MODE_OVERLAY = "overlay"
MODE_SMART = "smart"

MODE_LABELS = {
    MODE_KEEP: "保留原字幕",
    MODE_OVERLAY: "覆盖原字幕",
    MODE_SMART: "智能去除",
}


@dataclass(frozen=True)
class TimedRegion:
    start_ms: int
    end_ms: int
    text: str
    x: float
    y: float
    w: float
    h: float
    points: tuple[tuple[float, float], ...] = ()


@dataclass
class InpaintResult:
    output_path: Path
    subtitle_path: Path | None
    mode_requested: str
    mode_used: str
    recommended_mode: str
    reason: str
    quality_score: float
    frames_processed: int
    used_ai: bool
    used_fast: bool
    person_risk: float
    residual_text: bool
    comparison_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0
    used_temporal: bool = False
