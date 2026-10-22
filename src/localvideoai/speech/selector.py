"""Pick a local Whisper model and device from measured hardware."""

from __future__ import annotations

from dataclasses import dataclass

from localvideoai.hardware.hardware_manager import EnvironmentReport


@dataclass(frozen=True)
class ModelChoice:
    model_id: str
    device: str
    compute_type: str
    reason: str


# Multilingual Whisper only. Distil-large-v3 is English-centric and is not used.
_GPU_STRONG = "large-v3-turbo"
_GPU_MEDIUM = "medium"
_GPU_MID = "small"
_CPU = "small"
_CPU_LIGHT = "tiny"


def select_speech_model(
    report: EnvironmentReport,
    *,
    prefer_gpu: bool = True,
    device_preference: str = "auto",
    available: set[str] | None = None,
) -> ModelChoice:
    nvidia = _best_nvidia(report)
    want_gpu = device_preference == "gpu" or (device_preference == "auto" and prefer_gpu and nvidia is not None)
    if want_gpu and nvidia is None:
        want_gpu = False
    vram = nvidia.vram_mb if nvidia else 0
    if want_gpu:
        preferred = _GPU_STRONG if (vram or 0) >= 6000 else _GPU_MID
        compute = "float16"
        device = "cuda"
        reason = f"NVIDIA {nvidia.name if nvidia else 'GPU'} VRAM={vram}MB → {preferred} {compute}"
    else:
        ram = report.ram_total_gb or 0
        preferred = _CPU if ram > 8 else _CPU_LIGHT
        compute = "int8"
        device = "cpu"
        reason = f"CPU RAM={ram}GB → {preferred} {compute}"
    chosen = _first_available(preferred, available, device)
    if chosen != preferred:
        reason += f"；本地没有 {preferred}，改用 {chosen}"
    return ModelChoice(model_id=chosen, device=device, compute_type=compute, reason=reason)


def _best_nvidia(report: EnvironmentReport):
    nvidia = [gpu for gpu in report.gpus if "nvidia" in (gpu.name or "").lower() or gpu.cuda_driver_version]
    if not nvidia:
        return None
    return max(nvidia, key=lambda item: item.vram_mb or 0)


def _first_available(preferred: str, available: set[str] | None, device: str) -> str:
    if not available:
        return preferred
    order = [preferred, _GPU_STRONG, _GPU_MEDIUM, _GPU_MID, _CPU, _CPU_LIGHT]
    seen: set[str] = set()
    for name in order:
        if name in seen:
            continue
        seen.add(name)
        if name in available:
            return name
    if device == "cpu" and _CPU_LIGHT in available:
        return _CPU_LIGHT
    raise RuntimeError(f"本地没有可用的语音模型，需要其中之一：{sorted(available or {preferred, _CPU_LIGHT})}")
