"""Recommend models from measured CPU / GPU / RAM / VRAM. Not random."""

from __future__ import annotations

from localvideoai.hardware.hardware_manager import EnvironmentReport, GpuInfo
from localvideoai.speech.selector import select_speech_model


def best_nvidia(report: EnvironmentReport) -> GpuInfo | None:
    nvidia = [gpu for gpu in report.gpus if "nvidia" in (gpu.name or "").lower() or gpu.cuda_driver_version]
    if not nvidia:
        return None
    return max(nvidia, key=lambda item: item.vram_mb or 0)


def recommend_model_ids(report: EnvironmentReport) -> set[str]:
    recommended: set[str] = set()
    ram = report.ram_total_gb or 0
    gpu = best_nvidia(report)
    vram_mb = gpu.vram_mb or 0 if gpu else 0
    speech = select_speech_model(report, prefer_gpu=True, device_preference="auto")
    recommended.add(f"speech/{speech.model_id}")
    if ram < 8 or (gpu is None and ram < 8):
        recommended.add("speech/tiny")
    if ram >= 2:
        recommended.add("ocr/ppocrv6-small")
    if ram >= 4:
        recommended.add("translation/argos-zh-en")
        recommended.add("translation/argos-en-zh")
        recommended.add("speaker/3dspeaker-eres2net-zh-16k")
    if vram_mb >= 4000 or ram >= 8:
        recommended.add("inpaint/carve-lama-onnx-fp32")
    return recommended


def recommend_reason(report: EnvironmentReport) -> str:
    ram = report.ram_total_gb or 0
    gpu = best_nvidia(report)
    if gpu is None:
        return f"CPU {report.cpu_name or '本机'}，RAM {ram:.1f} GB，无可用 NVIDIA GPU → 推荐小模型"
    vram = gpu.vram_mb or 0
    return (
        f"CPU {report.cpu_name or '本机'}，RAM {ram:.1f} GB，"
        f"GPU {gpu.name} VRAM {vram} MB → 按显存/内存推荐"
    )
