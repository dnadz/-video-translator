from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from localvideoai.core.paths import install_root

_NVIDIA_SMI_CANDIDATES = (
    Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe",
)


def _run(command: list[str], timeout: int = 20) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
            "command": command,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": f"timeout after {timeout}s",
            "command": command,
        }
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": command,
    }


def _which(name: str) -> str | None:
    found = shutil.which(name)
    return str(Path(found)) if found else None


@dataclass
class GpuInfo:
    name: str
    vram_mb: int | None
    driver: str | None
    cuda_driver_version: str | None
    source: str
    notes: list[str] = field(default_factory=list)


@dataclass
class ToolInfo:
    name: str
    found: bool
    version: str | None = None
    path: str | None = None
    notes: str | None = None


@dataclass
class EnvironmentReport:
    os_caption: str
    os_version: str
    os_build: str
    os_arch: str
    python_version: str
    python_executable: str
    cpu_name: str
    cpu_cores: int | None
    cpu_logical: int | None
    ram_total_gb: float
    ram_available_gb: float | None
    disks: list[dict[str, Any]]
    gpus: list[GpuInfo]
    tools: list[ToolInfo]
    project_root: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


class HardwareManager:
    """Detect local hardware and developer tools. Does not enable remote APIs."""

    def detect(self) -> EnvironmentReport:
        notes: list[str] = []
        uname = platform.uname()
        os_caption = self._os_caption()
        if not os_caption:
            edition = ""
            if hasattr(platform, "win32_edition"):
                try:
                    edition = platform.win32_edition() or ""
                except OSError as exc:
                    notes.append(f"win32_edition failed: {exc}")
            os_caption = " ".join(part for part in ("Windows", uname.release, edition) if part)
        ram_total, ram_avail = self._memory()
        cpu_name, cores, logical = self._cpu()
        gpus = self._gpus()
        if not gpus:
            notes.append("No GPU was detected.")
        tools = self._tools()
        return EnvironmentReport(
            os_caption=os_caption,
            os_version=uname.version,
            os_build=uname.version,
            os_arch=platform.machine(),
            python_version=platform.python_version(),
            python_executable=sys.executable,
            cpu_name=cpu_name,
            cpu_cores=cores,
            cpu_logical=logical,
            ram_total_gb=ram_total,
            ram_available_gb=ram_avail,
            disks=self._disks(),
            gpus=gpus,
            tools=tools,
            project_root=str(install_root()),
            notes=notes,
        )

    def write_markdown(self, destination: Path, report: EnvironmentReport | None = None) -> Path:
        report = report or self.detect()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self._render_markdown(report), encoding="utf-8")
        return destination

    def _powershell(self) -> Path:
        return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"

    def _os_caption(self) -> str:
        result = _run(
            [
                str(self._powershell()),
                "-NoProfile",
                "-Command",
                "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); (Get-CimInstance Win32_OperatingSystem).Caption",
            ]
        )
        if result["ok"] and result["stdout"].strip():
            return result["stdout"].strip().splitlines()[-1].strip()
        return ""

    def _memory(self) -> tuple[float, float | None]:
        import ctypes

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
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("GlobalMemoryStatusEx failed")
        total = round(status.ullTotalPhys / (1024**3), 2)
        avail = round(status.ullAvailPhys / (1024**3), 2)
        return total, avail

    def _cpu(self) -> tuple[str, int | None, int | None]:
        logical = os.cpu_count()
        name = platform.processor() or "Unknown CPU"
        cores = None
        result = _run(
            [
                str(self._powershell()),
                "-NoProfile",
                "-Command",
                "$p = Get-CimInstance Win32_Processor | Select-Object -First 1; "
                "Write-Output $p.Name; Write-Output $p.NumberOfCores; Write-Output $p.NumberOfLogicalProcessors",
            ]
        )
        if result["ok"]:
            lines = [ln.strip() for ln in result["stdout"].splitlines() if ln.strip()]
            if len(lines) >= 3:
                name = lines[0]
                if lines[1].isdigit():
                    cores = int(lines[1])
                if lines[2].isdigit():
                    logical = int(lines[2])
                return name, cores, logical
        wmic = _run(
            [
                str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wbem" / "wmic.exe"),
                "cpu",
                "get",
                "Name,NumberOfCores,NumberOfLogicalProcessors",
                "/format:list",
            ]
        )
        if wmic["ok"]:
            parsed: dict[str, str] = {}
            for line in wmic["stdout"].splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    parsed[key.strip()] = value.strip()
            name = parsed.get("Name") or name
            if parsed.get("NumberOfCores", "").isdigit():
                cores = int(parsed["NumberOfCores"])
            if parsed.get("NumberOfLogicalProcessors", "").isdigit():
                logical = int(parsed["NumberOfLogicalProcessors"])
        return name, cores, logical

    def _disks(self) -> list[dict[str, Any]]:
        disks: list[dict[str, Any]] = []
        for letter in "CDEFGHIJ":
            drive = Path(f"{letter}:/")
            if not drive.exists():
                continue
            usage = shutil.disk_usage(drive)
            disks.append(
                {
                    "drive": f"{letter}:",
                    "total_gb": round(usage.total / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                }
            )
        return disks

    def _gpus(self) -> list[GpuInfo]:
        gpus: list[GpuInfo] = []
        smi_path = _which("nvidia-smi")
        if smi_path is None:
            for candidate in _NVIDIA_SMI_CANDIDATES:
                if candidate.is_file():
                    smi_path = str(candidate)
                    break
        if smi_path:
            query = _run(
                [
                    smi_path,
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ]
            )
            cuda = _run([smi_path])
            cuda_version = None
            if cuda["ok"]:
                for line in cuda["stdout"].splitlines():
                    if "CUDA Version" in line:
                        cuda_version = line.split("CUDA Version:")[-1].split()[0]
                        break
            if query["ok"] and query["stdout"]:
                for row in query["stdout"].splitlines():
                    parts = [p.strip() for p in row.split(",")]
                    if len(parts) >= 3:
                        try:
                            vram = int(float(parts[1]))
                        except ValueError:
                            vram = None
                        gpus.append(
                            GpuInfo(
                                name=parts[0],
                                vram_mb=vram,
                                driver=parts[2],
                                cuda_driver_version=cuda_version,
                                source=smi_path,
                            )
                        )
            elif query["stderr"]:
                gpus.append(
                    GpuInfo(
                        name="NVIDIA GPU (query failed)",
                        vram_mb=None,
                        driver=None,
                        cuda_driver_version=cuda_version,
                        source=smi_path,
                        notes=[query["stderr"]],
                    )
                )
        if gpus:
            return gpus
        wmic = _run(
            [
                str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wbem" / "wmic.exe"),
                "path",
                "win32_VideoController",
                "get",
                "Name,AdapterRAM,DriverVersion",
                "/format:list",
            ]
        )
        if wmic["ok"]:
            block: dict[str, str] = {}
            for line in wmic["stdout"].splitlines() + [""]:
                if "=" in line:
                    key, value = line.split("=", 1)
                    block[key.strip()] = value.strip()
                    continue
                if block.get("Name"):
                    vram = None
                    notes = [
                        "WMI AdapterRAM is often capped near 4 GB; prefer nvidia-smi when available."
                    ]
                    if block.get("AdapterRAM", "").isdigit():
                        vram = int(int(block["AdapterRAM"]) / (1024 * 1024))
                    gpus.append(
                        GpuInfo(
                            name=block["Name"],
                            vram_mb=vram,
                            driver=block.get("DriverVersion"),
                            cuda_driver_version=None,
                            source="WMI",
                            notes=notes,
                        )
                    )
                    block = {}
        return gpus

    def _tools(self) -> list[ToolInfo]:
        tools: list[ToolInfo] = []
        git = _which("git")
        if git:
            result = _run([git, "--version"])
            tools.append(
                ToolInfo("git", True, result["stdout"] or None, git, None if result["ok"] else result["stderr"])
            )
        else:
            tools.append(ToolInfo("git", False))

        tools.append(
            ToolInfo(
                "python",
                True,
                platform.python_version(),
                sys.executable,
            )
        )

        ffmpeg = _which("ffmpeg")
        if not ffmpeg:
            try:
                from localvideoai.core.exceptions import MediaError
                from localvideoai.media.ffmpeg_runtime import find_ffmpeg

                ffmpeg = str(find_ffmpeg())
            except MediaError:
                ffmpeg = None
        if ffmpeg:
            result = _run([ffmpeg, "-version"])
            first = result["stdout"].splitlines()[0] if result["stdout"] else None
            tools.append(ToolInfo("ffmpeg", True, first, ffmpeg, "bundled or PATH"))
        else:
            tools.append(
                ToolInfo(
                    "ffmpeg",
                    False,
                    notes="Not found on PATH or in vendor/ffmpeg. Playback still uses Qt bundled FFmpeg libraries.",
                )
            )

        for name in ("cl", "gcc", "cmake", "nvcc", "rustc"):
            path = _which(name)
            if path:
                result = _run([path, "--version"] if name != "cl" else [path])
                version = (result["stdout"] or result["stderr"] or "").splitlines()
                tools.append(ToolInfo(name, True, version[0] if version else None, path))
            else:
                extra = None
                if name == "nvcc":
                    extra = "CUDA toolkit compiler not found. Driver CUDA version is still reported by nvidia-smi if present."
                elif name == "cl":
                    extra = "MSVC compiler is not on PATH. Binary wheels will be used; users will not be asked to install a compiler."
                tools.append(ToolInfo(name, False, notes=extra))
        return tools

    def _render_markdown(self, report: EnvironmentReport) -> str:
        lines = [
            "# Environment Report",
            "",
            "Generated by HardwareManager during Phase 0. Values are measured on this machine, not guessed.",
            "",
            "## Operating system",
            "",
            f"- Caption: {report.os_caption}",
            f"- Version: {report.os_version}",
            f"- Architecture: {report.os_arch}",
            "",
            "## Python",
            "",
            f"- Version: {report.python_version}",
            f"- Executable: `{report.python_executable}`",
            "",
            "## CPU",
            "",
            f"- Name: {report.cpu_name}",
            f"- Cores: {report.cpu_cores}",
            f"- Logical processors: {report.cpu_logical}",
            "",
            "## Memory",
            "",
            f"- Total RAM: {report.ram_total_gb} GB",
            f"- Available RAM: {report.ram_available_gb} GB",
            "",
            "## Disks",
            "",
        ]
        for disk in report.disks:
            lines.append(
                f"- {disk['drive']} total {disk['total_gb']} GB, free {disk['free_gb']} GB"
            )
        lines.extend(["", "## GPU", ""])
        if not report.gpus:
            lines.append("- None detected")
        for gpu in report.gpus:
            vram = f"{gpu.vram_mb} MB" if gpu.vram_mb is not None else "unknown"
            lines.append(f"- Name: {gpu.name}")
            lines.append(f"- VRAM: {vram}")
            lines.append(f"- Driver: {gpu.driver}")
            lines.append(f"- CUDA driver version: {gpu.cuda_driver_version}")
            lines.append(f"- Source: `{gpu.source}`")
            for note in gpu.notes:
                lines.append(f"- Note: {note}")
        lines.extend(["", "## Tools", ""])
        for tool in report.tools:
            status = "found" if tool.found else "missing"
            detail = tool.version or tool.notes or ""
            path = f" (`{tool.path}`)" if tool.path else ""
            lines.append(f"- {tool.name}: {status}{path} {detail}".rstrip())
        lines.extend(["", "## Project root", "", f"- `{report.project_root}`", ""])
        if report.notes:
            lines.extend(["## Notes", ""])
            for note in report.notes:
                lines.append(f"- {note}")
            lines.append("")
        return "\n".join(lines) + "\n"
