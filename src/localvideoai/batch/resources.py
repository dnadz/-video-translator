"""Read CPU / GPU preference and RAM so the queue can refuse extra work."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceSnapshot:
    total_ram_gb: float
    available_ram_gb: float
    cpu_count: int
    device: str
    prefer_gpu: bool
    max_concurrent: int
    ram_limit_gb: float
    min_free_ram_gb: float
    cpu_threads: int


def snapshot(
    *,
    device: str = "auto",
    prefer_gpu: bool = True,
    max_concurrent: int = 1,
    ram_limit_gb: float = 0.0,
    min_free_ram_gb: float = 1.5,
    cpu_threads: int = 0,
) -> ResourceSnapshot:
    total, available = physical_memory_gb()
    return ResourceSnapshot(
        total_ram_gb=total,
        available_ram_gb=available,
        cpu_count=os.cpu_count() or 1,
        device=(device or "auto").strip().lower(),
        prefer_gpu=bool(prefer_gpu),
        max_concurrent=max(1, int(max_concurrent or 1)),
        ram_limit_gb=max(0.0, float(ram_limit_gb or 0.0)),
        min_free_ram_gb=max(0.0, float(min_free_ram_gb or 0.0)),
        cpu_threads=max(0, int(cpu_threads or 0)),
    )


def can_start_another(running: int, limits: ResourceSnapshot) -> tuple[bool, str]:
    if running >= limits.max_concurrent:
        return False, f"并发已达 {limits.max_concurrent}"
    _total, available = physical_memory_gb()
    if limits.min_free_ram_gb and available < limits.min_free_ram_gb:
        return False, f"可用内存 {available:.1f} GB，低于下限 {limits.min_free_ram_gb:.1f} GB"
    used = max(0.0, limits.total_ram_gb - available)
    if limits.ram_limit_gb and used >= limits.ram_limit_gb:
        return False, f"已用内存 {used:.1f} GB，达到上限 {limits.ram_limit_gb:.1f} GB"
    return True, ""


def physical_memory_gb() -> tuple[float, float]:
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("GlobalMemoryStatusEx failed")
        return status.ullTotalPhys / 1e9, status.ullAvailPhys / 1e9
    except Exception:
        return 0.0, 0.0
