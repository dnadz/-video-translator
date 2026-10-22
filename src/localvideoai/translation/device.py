"""Pick CPU or CUDA for CTranslate2 translation."""

from __future__ import annotations

from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.speech.cuda_runtime import prepare_cuda_dlls


def nvidia_available(report: EnvironmentReport | None) -> bool:
    if report is None:
        return False
    for gpu in report.gpus or []:
        name = (gpu.name or "").lower()
        if gpu.cuda_driver_version:
            return True
        if any(token in name for token in ("nvidia", "geforce", "rtx", "quadro", "tesla")):
            return True
    return False


def resolve_translation_device(
    report: EnvironmentReport | None,
    device_preference: str = "auto",
    prefer_gpu: bool = True,
) -> tuple[str, str]:
    preference = (device_preference or "auto").strip().lower()
    if preference == "cpu":
        return "cpu", "int8"
    live = report
    if live is None:
        from localvideoai.hardware.hardware_manager import HardwareManager

        live = HardwareManager().detect()
    want_gpu = preference == "gpu" or (preference == "auto" and prefer_gpu and nvidia_available(live))
    if want_gpu:
        prepare_cuda_dlls()
        return "cuda", "float16"
    return "cpu", "int8"
