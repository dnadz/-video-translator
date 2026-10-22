"""Locate pip-installed NVIDIA CUDA 12 DLLs so CTranslate2 can use the GPU."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from localvideoai.managers.log_manager import get_logger

_PREPARED = False
_ADDED: list[str] = []
_DLL_LAYOUTS = ("cublas/bin", "cudnn/bin", "cuda_nvrtc/bin", "cuda_runtime/bin")
_CUDA_MARKERS = ("cublas", "cudnn", "cudart", "nvrtc", "cuda error", "out of memory")


def is_cuda_runtime_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _CUDA_MARKERS)


def prepare_cuda_dlls() -> list[str]:
    """Add each CUDA directory once. Repeating this grows PATH until Windows returns WinError 8."""
    global _PREPARED, _ADDED
    if _PREPARED:
        return list(_ADDED)
    added: list[str] = []
    existing = {item for item in os.environ.get("PATH", "").split(os.pathsep) if item}
    candidates = _dll_directories()
    seen: set[Path] = set()
    for directory in candidates:
        try:
            resolved = directory.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        path_text = str(resolved)
        if path_text not in existing:
            os.environ["PATH"] = path_text + os.pathsep + os.environ.get("PATH", "")
            existing.add(path_text)
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(path_text)
            except OSError:
                continue
        added.append(path_text)
    if added:
        get_logger("speech").info("CUDA DLL directories: %s", added)
    _ADDED = added
    _PREPARED = True
    return list(_ADDED)


def _dll_directories() -> list[Path]:
    candidates: list[Path] = []
    for nvidia_root in _nvidia_roots():
        for pattern in _DLL_LAYOUTS:
            direct = nvidia_root / pattern.replace("/", os.sep)
            if direct.is_dir():
                candidates.append(direct)
            package_bin = nvidia_root / pattern.split("/")[0] / "bin"
            if package_bin.is_dir():
                candidates.append(package_bin)
                for child in package_bin.iterdir():
                    if child.is_dir():
                        candidates.append(child)
    for folder in _application_dirs():
        if _contains_cublas(folder):
            candidates.append(folder)
    return candidates


def _nvidia_roots() -> list[Path]:
    roots: list[Path] = []
    for item in sys.path:
        if not item:
            continue
        path = Path(item)
        roots.append(path if path.name == "nvidia" else path / "nvidia")
    try:
        import nvidia

        roots.append(Path(nvidia.__file__).resolve().parent)
    except Exception:
        pass
    for folder in _application_dirs():
        roots.append(folder / "nvidia")
        roots.append(folder / "_internal" / "nvidia")
    for start in _application_dirs():
        hops = [start, *list(start.parents)[:6]]
        for candidate in hops:
            for venv_name in (".venv", "venv"):
                roots.append(candidate / venv_name / "Lib" / "site-packages" / "nvidia")
    return roots


def _application_dirs() -> list[Path]:
    found: list[Path] = []
    found.append(Path(sys.executable).resolve().parent)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        found.append(Path(meipass))
    try:
        from localvideoai.core.paths import bundle_root, install_root

        found.append(install_root())
        found.append(bundle_root())
    except Exception:
        pass
    return found


def _contains_cublas(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    return any(folder.glob("cublas64_*.dll"))
