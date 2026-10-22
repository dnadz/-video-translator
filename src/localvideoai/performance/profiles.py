"""Hardware profiles used to adapt performance. Low / mid / high can be simulated."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from localvideoai.hardware.hardware_manager import EnvironmentReport, GpuInfo
from localvideoai.models.recommend import best_nvidia

PROFILE_IDS = ("low", "mid", "high")
SIMULATE_ENV = "LOCALVIDEOAI_SIMULATE_PROFILE"


@dataclass(frozen=True)
class HardwareProfile:
    profile_id: str
    label: str
    ram_gb: float
    has_gpu: bool
    vram_mb: int
    gpu_name: str
    notes: str


LOW = HardwareProfile(
    profile_id="low",
    label="低配置",
    ram_gb=8.0,
    has_gpu=False,
    vram_mb=0,
    gpu_name="",
    notes="CPU，8GB RAM，无 GPU。基础功能走 CPU 小模型。",
)
MID = HardwareProfile(
    profile_id="mid",
    label="中配置",
    ram_gb=16.0,
    has_gpu=True,
    vram_mb=4096,
    gpu_name="Simulated Mid GPU",
    notes="CPU，16GB RAM，中等 GPU（约 4GB VRAM）。",
)
HIGH = HardwareProfile(
    profile_id="high",
    label="高配置",
    ram_gb=32.0,
    has_gpu=True,
    vram_mb=10240,
    gpu_name="Simulated High GPU",
    notes="CPU，32GB RAM，中高端 GPU。自动使用 GPU。",
)

PROFILES = {"low": LOW, "mid": MID, "high": HIGH}


def normalize_profile_id(value: str | None) -> str:
    key = (value or "").strip().lower()
    if key in PROFILES:
        return key
    raise ValueError(f"未知性能档位：{value}（需要 low / mid / high）")


def classify_profile(report: EnvironmentReport) -> HardwareProfile:
    """Map a measured (or simulated) report onto low / mid / high."""
    gpu = best_nvidia(report)
    ram = float(report.ram_total_gb or 0)
    vram = int(gpu.vram_mb or 0) if gpu is not None else 0
    if gpu is None or vram <= 0:
        return LOW if ram <= 12 else MID
    if ram <= 10 and vram < 2048:
        return LOW
    if ram >= 24 and vram >= 6000:
        return HIGH
    return MID


def simulate_report(profile_id: str, base: EnvironmentReport | None = None) -> EnvironmentReport:
    """Build a report that matches the requested hardware class. CPU name can stay real."""
    spec = PROFILES[normalize_profile_id(profile_id)]
    template = base or _blank_report()
    gpus: list[GpuInfo] = []
    if spec.has_gpu:
        gpus = [
            GpuInfo(
                name=spec.gpu_name,
                vram_mb=spec.vram_mb,
                driver="simulated",
                cuda_driver_version="12.4",
                source="phase19-simulate",
                notes=["simulated hardware profile"],
            )
        ]
    notes = list(template.notes)
    notes.append(f"simulated profile={spec.profile_id}")
    return replace(
        template,
        ram_total_gb=spec.ram_gb,
        ram_available_gb=round(spec.ram_gb * 0.55, 2),
        gpus=gpus,
        notes=notes,
    )


def apply_simulation(report: EnvironmentReport, profile_id: str | None = None) -> EnvironmentReport:
    chosen = (profile_id or os.environ.get(SIMULATE_ENV) or "").strip().lower()
    if not chosen:
        return report
    if chosen not in PROFILES:
        return report
    return simulate_report(chosen, report)


def _blank_report() -> EnvironmentReport:
    return EnvironmentReport(
        os_caption="Windows 11 Simulated",
        os_version="10.0.22000",
        os_build="22000",
        os_arch="AMD64",
        python_version="3.12.13",
        python_executable="python",
        cpu_name="Simulated CPU",
        cpu_cores=4,
        cpu_logical=8,
        ram_total_gb=8.0,
        ram_available_gb=4.0,
        disks=[],
        gpus=[],
        tools=[],
        project_root=".",
    )
