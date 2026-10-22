"""Resolve application paths without machine-specific hardcoded locations."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from localvideoai import APP_NAME
from localvideoai.core.exceptions import PathError

_ENV_ROOT = "LOCALVIDEOAI_ROOT"
_ENV_DATA = "LOCALVIDEOAI_DATA_DIR"
_ENV_LOG = "LOCALVIDEOAI_LOG_DIR"
_ENV_CONFIG = "LOCALVIDEOAI_CONFIG_PATH"
_ENV_MODELS = "LOCALVIDEOAI_MODELS_DIR"
_ENV_PROJECTS = "LOCALVIDEOAI_PROJECTS_DIR"
_ENV_CACHE = "LOCALVIDEOAI_CACHE_DIR"
_ENV_PORTABLE = "LOCALVIDEOAI_PORTABLE"
_ENV_SKIP_BUNDLED = "LOCALVIDEOAI_SKIP_BUNDLED_MODELS"
_INSTALL_PATHS_NAME = "install_paths.json"
_PORTABLE_FLAG = "portable.flag"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _walk_to_project_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        marker = candidate / "pyproject.toml"
        src = candidate / "src" / "localvideoai"
        if marker.is_file() and src.is_dir():
            return candidate
    return None


def install_root() -> Path:
    """Directory that contains the application (source tree or EXE folder)."""
    override = os.environ.get(_ENV_ROOT)
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_dir():
            raise PathError(f"{_ENV_ROOT} is not a directory: {path}")
        return path
    if is_frozen():
        return Path(sys.executable).resolve().parent
    found = _walk_to_project_root(Path(__file__).resolve())
    if found is None:
        raise PathError("Cannot locate project root from source files.")
    return found


def bundle_root() -> Path:
    """PyInstaller extract dir, or the same as install_root() when running from source."""
    meipass = getattr(sys, "_MEIPASS", None)
    if is_frozen() and meipass:
        return Path(meipass)
    return install_root()


def is_portable() -> bool:
    if os.environ.get(_ENV_PORTABLE, "").strip() == "1":
        return True
    return (install_root() / _PORTABLE_FLAG).is_file()


def _raw_user_data_dir() -> Path:
    override = os.environ.get(_ENV_DATA)
    if override:
        return Path(override).expanduser().resolve()
    if is_portable():
        return install_root() / "data"
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        return Path(local_app) / APP_NAME
    return Path.home() / "AppData" / "Local" / APP_NAME


def install_paths_file() -> Path:
    if is_frozen():
        return install_root() / _INSTALL_PATHS_NAME
    return _raw_user_data_dir() / _INSTALL_PATHS_NAME


def load_install_paths() -> dict[str, str]:
    merged: dict[str, str] = {}
    candidates = [_raw_user_data_dir() / _INSTALL_PATHS_NAME]
    if is_frozen():
        candidates.insert(0, install_root() / _INSTALL_PATHS_NAME)
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            merged.update({str(key): str(value) for key, value in data.items() if value})
    return merged


def write_install_paths(values: dict[str, Any]) -> Path:
    payload = {key: str(value) for key, value in values.items() if value}
    destination = install_paths_file()
    ensure_directory(destination.parent)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def _first_existing_file(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def default_config_path() -> Path:
    return _first_existing_file(
        install_root() / "config" / "default.json",
        bundle_root() / "config" / "default.json",
    )


def user_data_dir() -> Path:
    override = os.environ.get(_ENV_DATA)
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        mapped = load_install_paths().get("data_dir")
        if mapped:
            return Path(mapped).expanduser().resolve()
    return _raw_user_data_dir()


def user_config_path() -> Path:
    override = os.environ.get(_ENV_CONFIG)
    if override:
        return Path(override).expanduser().resolve()
    return user_data_dir() / "settings.json"


def logs_dir() -> Path:
    override = os.environ.get(_ENV_LOG)
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        return user_data_dir() / "logs"
    return install_root() / "logs"


def bundled_models_dir() -> Path:
    """Read-only deployed models next to the software tree. Not the write target."""
    for root in (install_root(), bundle_root()):
        candidate = root / "models"
        if candidate.is_dir():
            return candidate
    return install_root() / "models"


def models_root_pointer_path() -> Path:
    return user_data_dir() / "models_root.txt"


def managed_models_dir() -> Path:
    """Writable independent model root. Large files must not live in the install tree."""
    override = os.environ.get(_ENV_MODELS)
    if override:
        return Path(override).expanduser().resolve()
    mapped = load_install_paths().get("models_dir")
    if mapped:
        return Path(mapped).expanduser().resolve()
    pointer = models_root_pointer_path()
    if pointer.is_file():
        text = pointer.read_text(encoding="utf-8").strip()
        if text:
            return Path(text).expanduser().resolve()
    return user_data_dir() / "models"


def set_managed_models_dir(path: Path) -> Path:
    """Persist a user-chosen model directory for this machine."""
    resolved = Path(path).expanduser().resolve()
    ensure_directory(resolved)
    if resolved == bundled_models_dir().resolve():
        raise PathError("不能把软件安装目录当作可写模型目录。请选择独立目录。")
    pointer = models_root_pointer_path()
    ensure_directory(pointer.parent)
    pointer.write_text(str(resolved), encoding="utf-8")
    current = load_install_paths()
    current["models_dir"] = str(resolved)
    write_install_paths(current)
    return resolved


def config_file(name: str) -> Path:
    return _first_existing_file(
        install_root() / "config" / name,
        bundle_root() / "config" / name,
    )


def models_dir() -> Path:
    """Primary writable model root (managed / user-data, not the software tree)."""
    return managed_models_dir()


def skip_bundled_models() -> bool:
    return os.environ.get(_ENV_SKIP_BUNDLED) == "1"


def model_search_roots() -> list[Path]:
    """Managed root first, then the software-tree deploy if it is a different folder."""
    roots: list[Path] = []
    managed = managed_models_dir()
    roots.append(managed)
    if skip_bundled_models():
        return roots
    bundled = bundled_models_dir()
    try:
        if bundled.resolve() != managed.resolve() and bundled.is_dir():
            roots.append(bundled)
    except OSError:
        pass
    return roots


def speech_models_dir() -> Path:
    return models_dir() / "speech"


def ocr_models_dir() -> Path:
    return models_dir() / "ocr"


def translation_models_dir() -> Path:
    return models_dir() / "translation"


def speaker_models_dir() -> Path:
    return models_dir() / "speaker"


def inpaint_models_dir() -> Path:
    return models_dir() / "inpaint"


def projects_dir() -> Path:
    override = os.environ.get(_ENV_PROJECTS)
    if override:
        return Path(override).expanduser().resolve()
    mapped = load_install_paths().get("projects_dir")
    if mapped:
        return Path(mapped).expanduser().resolve()
    return user_data_dir() / "projects"


def cache_dir() -> Path:
    override = os.environ.get(_ENV_CACHE)
    if override:
        return Path(override).expanduser().resolve()
    mapped = load_install_paths().get("cache_dir")
    if mapped:
        return Path(mapped).expanduser().resolve()
    return user_data_dir() / "cache"


def set_projects_dir(path: Path) -> Path:
    resolved = ensure_directory(Path(path).expanduser().resolve())
    current = load_install_paths()
    current["projects_dir"] = str(resolved)
    write_install_paths(current)
    return resolved


def set_cache_dir(path: Path) -> Path:
    resolved = ensure_directory(Path(path).expanduser().resolve())
    current = load_install_paths()
    current["cache_dir"] = str(resolved)
    write_install_paths(current)
    return resolved


def translation_user_dir() -> Path:
    override = os.environ.get("LOCALVIDEOAI_TRANSLATION_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return user_data_dir() / "translation"


def transcripts_dir() -> Path:
    override = os.environ.get("LOCALVIDEOAI_TRANSCRIPT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return user_data_dir() / "transcripts"


def ocr_results_dir() -> Path:
    override = os.environ.get("LOCALVIDEOAI_OCR_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return user_data_dir() / "ocr"


def assets_dir() -> Path:
    return install_root() / "assets"


def database_path() -> Path:
    return user_data_dir() / "localvideoai.sqlite3"


def recovery_dir() -> Path:
    override = os.environ.get("LOCALVIDEOAI_RECOVERY_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return user_data_dir() / "recovery"


def vendor_dir() -> Path:
    return install_root() / "vendor"


def ffmpeg_dir() -> Path:
    override = os.environ.get("LOCALVIDEOAI_FFMPEG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    for root in (install_root(), bundle_root()):
        candidate = root / "vendor" / "ffmpeg"
        if candidate.is_dir() or (candidate / "bin" / "ffmpeg.exe").is_file():
            return candidate
    return install_root() / "vendor" / "ffmpeg"


def ensure_directory(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PathError(f"Cannot create directory: {path}") from exc
    return path
