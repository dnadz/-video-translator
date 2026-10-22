"""Facade used by UI and engines. Does not import model SDKs."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from localvideoai.hardware.hardware_manager import EnvironmentReport, GpuInfo
from localvideoai.models.recommend import best_nvidia
from localvideoai.performance.cache import configure_cache_limits, get_media_cache, get_model_cache
from localvideoai.performance.policy import PerformancePolicy, policy_from_report
from localvideoai.performance.profiles import apply_simulation, classify_profile
from localvideoai.performance.throttle import ProgressThrottle


class BackgroundGate:
    """Limit concurrent heavy jobs so low-RAM machines stay interactive."""

    def __init__(self, max_jobs: int) -> None:
        self.max_jobs = max(1, int(max_jobs))
        self._running: set[str] = set()
        self._lock = Lock()

    def try_acquire(self, name: str) -> bool:
        with self._lock:
            if name in self._running:
                return True
            if len(self._running) >= self.max_jobs:
                return False
            self._running.add(name)
            return True

    def release(self, name: str) -> None:
        with self._lock:
            self._running.discard(name)

    def running(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._running))


@dataclass(frozen=True)
class HardwareSnapshot:
    cpu: str
    gpu: str
    vram: str
    ram: str
    profile_label: str
    auto_gpu: bool

    def status_text(self) -> str:
        gpu_note = "自动GPU" if self.auto_gpu else "CPU"
        return (
            f"CPU：{self.cpu}  |  GPU：{self.gpu}  |  VRAM：{self.vram}  |  "
            f"RAM：{self.ram}  |  档位：{self.profile_label}（{gpu_note}）"
        )

    def detail_text(self) -> str:
        return (
            f"CPU：{self.cpu}\n"
            f"GPU：{self.gpu}\n"
            f"VRAM：{self.vram}\n"
            f"RAM：{self.ram}\n"
            f"档位：{self.profile_label}"
        )


class PerformanceRuntime:
    def __init__(self, report: EnvironmentReport) -> None:
        self.report = apply_simulation(report)
        self.profile = classify_profile(self.report)
        self.policy = policy_from_report(self.report)
        configure_cache_limits(self.policy.media_cache_size, self.policy.model_cache_size)
        self.jobs = BackgroundGate(self.policy.max_background_jobs)
        self.media_cache = get_media_cache()
        self.model_cache = get_model_cache()

    def snapshot(self) -> HardwareSnapshot:
        gpu = best_nvidia(self.report)
        ram_total = self.report.ram_total_gb or 0
        ram_avail = self.report.ram_available_gb
        ram = f"{ram_total:.1f} GB" if ram_avail is None else f"{ram_total:.1f} / {ram_avail:.1f} GB"
        return HardwareSnapshot(
            cpu=self.report.cpu_name or "未知 CPU",
            gpu=gpu.name if gpu is not None else "无",
            vram=_vram_text(gpu),
            ram=ram,
            profile_label=self.profile.label,
            auto_gpu=self.policy.auto_uses_gpu,
        )

    def throttle(self, emit) -> ProgressThrottle:
        return ProgressThrottle(self.policy.progress_min_interval_ms, emit)

    def busy_message(self) -> str:
        running = "、".join(self.jobs.running()) or "后台任务"
        return f"{self.profile.label}同时最多 {self.policy.max_background_jobs} 个后台任务，请等待{running}结束。"


def _vram_text(gpu: GpuInfo | None) -> str:
    if gpu is None or not gpu.vram_mb:
        return "无"
    return f"{gpu.vram_mb} MB"
