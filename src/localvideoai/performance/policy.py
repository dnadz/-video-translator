"""Adaptive limits derived from a hardware profile. Not random, not UI-bound."""

from __future__ import annotations

from dataclasses import dataclass, replace

from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.models.recommend import best_nvidia
from localvideoai.performance.profiles import (
    HardwareProfile,
    apply_simulation,
    classify_profile,
)


@dataclass(frozen=True)
class PerformancePolicy:
    profile_id: str
    label: str
    prefer_gpu: bool
    speech_device: str
    speech_compute: str
    speech_model_hint: str
    translation_device: str
    chunk_ms: int
    overlap_ms: int
    ocr_sample_fps: float
    word_timestamp_max_ms: int
    beam_size: int
    media_cache_size: int
    model_cache_size: int
    max_background_jobs: int
    progress_min_interval_ms: int
    reason: str

    @property
    def auto_uses_gpu(self) -> bool:
        return self.prefer_gpu and self.speech_device == "cuda"


def policy_for(profile: HardwareProfile) -> PerformancePolicy:
    if profile.profile_id == "low":
        return PerformancePolicy(
            profile_id="low",
            label=profile.label,
            prefer_gpu=False,
            speech_device="cpu",
            speech_compute="int8",
            speech_model_hint="tiny",
            translation_device="cpu",
            chunk_ms=20_000,
            overlap_ms=600,
            ocr_sample_fps=1.5,
            word_timestamp_max_ms=5 * 60 * 1000,
            beam_size=1,
            media_cache_size=8,
            model_cache_size=1,
            max_background_jobs=1,
            progress_min_interval_ms=200,
            reason="低配置：CPU + tiny，缩小分段和 OCR 帧率，限制后台任务，保证基础功能可用",
        )
    if profile.profile_id == "high":
        return PerformancePolicy(
            profile_id="high",
            label=profile.label,
            prefer_gpu=True,
            speech_device="cuda",
            speech_compute="float16",
            speech_model_hint="large-v3-turbo",
            translation_device="cuda",
            chunk_ms=30_000,
            overlap_ms=800,
            ocr_sample_fps=4.0,
            word_timestamp_max_ms=15 * 60 * 1000,
            beam_size=5,
            media_cache_size=32,
            model_cache_size=3,
            max_background_jobs=2,
            progress_min_interval_ms=80,
            reason="高配置：自动使用 GPU，更大缓存，词级时间戳窗口更长",
        )
    return PerformancePolicy(
        profile_id="mid",
        label=profile.label,
        prefer_gpu=True,
        speech_device="cuda",
        speech_compute="float16",
        speech_model_hint="small",
        translation_device="cuda",
        chunk_ms=30_000,
        overlap_ms=800,
        ocr_sample_fps=3.0,
        word_timestamp_max_ms=15 * 60 * 1000,
        beam_size=3,
        media_cache_size=16,
        model_cache_size=2,
        max_background_jobs=2,
        progress_min_interval_ms=120,
        reason="中配置：自动尝试 GPU + small，平衡速度与内存",
    )


def policy_from_report(report: EnvironmentReport | None) -> PerformancePolicy:
    if report is None:
        from localvideoai.performance.profiles import MID

        return policy_for(MID)
    live = apply_simulation(report)
    policy = policy_for(classify_profile(live))
    if best_nvidia(live) is None:
        return replace(
            policy,
            prefer_gpu=False,
            speech_device="cpu",
            speech_compute="int8",
            translation_device="cpu",
            reason=f"{policy.reason}；当前没有可用 GPU，改用 CPU",
        )
    return policy


def basic_capabilities(policy: PerformancePolicy) -> tuple[str, ...]:
    """Features that must remain usable on this profile."""
    common = ("analyze", "playback", "subtitle_import", "export_remux")
    if policy.profile_id == "low":
        return (*common, "transcribe_cpu", "translate_cpu")
    return (*common, "transcribe_auto", "translate_auto", "ocr")
