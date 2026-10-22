"""Map user delay + profile to a real processing window. Adjusts from measured time."""

from __future__ import annotations

from dataclasses import dataclass

DELAY_OPTIONS_MS = (1000, 3000, 5000, 10000, 30000)
PROFILE_IDS = ("low", "fast", "balanced", "accurate")
PROFILE_LABELS = {
    "low": "低延迟",
    "fast": "快速",
    "balanced": "平衡",
    "accurate": "准确",
}


@dataclass(frozen=True)
class LatencyProfile:
    profile_id: str
    label: str
    min_ms: int
    max_ms: int
    overlap_ms: int
    asr_beam: int
    translation_quality: str
    word_timestamps: bool
    prefer_tiny: bool
    accurate_seek: bool


_PROFILES = {
    "low": LatencyProfile("low", "低延迟", 800, 5000, 200, 1, "fast", False, True, False),
    "fast": LatencyProfile("fast", "快速", 1000, 10000, 300, 1, "fast", False, False, False),
    "balanced": LatencyProfile("balanced", "平衡", 2000, 20000, 400, 2, "standard", False, False, False),
    "accurate": LatencyProfile("accurate", "准确", 3000, 30000, 800, 5, "high", True, False, True),
}


def normalize_profile(value: str | None) -> str:
    key = (value or "balanced").strip().lower()
    aliases = {"低延迟": "low", "快速": "fast", "平衡": "balanced", "准确": "accurate"}
    key = aliases.get(key, key)
    if key not in _PROFILES:
        return "balanced"
    return key


def normalize_delay_ms(value: int | None) -> int:
    if value is None:
        return 3000
    nearest = min(DELAY_OPTIONS_MS, key=lambda item: abs(item - int(value)))
    return nearest


def profile_settings(value: str | None) -> LatencyProfile:
    return _PROFILES[normalize_profile(value)]


def adjust_window_ms(
    requested_ms: int,
    profile: str | LatencyProfile,
    last_process_ms: int | None = None,
) -> int:
    """Clamp the user delay to the profile, then grow if the last job was too slow."""
    settings = profile if isinstance(profile, LatencyProfile) else profile_settings(profile)
    requested = max(200, int(requested_ms))
    window = min(settings.max_ms, max(settings.min_ms, requested))
    if last_process_ms is None:
        return window
    elapsed = max(0, int(last_process_ms))
    if elapsed > int(window * 0.9):
        grown = int(elapsed * 1.2)
        return min(settings.max_ms, max(window, grown))
    if elapsed < int(window * 0.35) and requested < window:
        return max(settings.min_ms, requested)
    return window
