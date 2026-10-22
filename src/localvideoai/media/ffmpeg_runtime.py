from __future__ import annotations

import os
import shutil
from pathlib import Path

from localvideoai.core.exceptions import MediaError
from localvideoai.core.paths import ffmpeg_dir, install_root


def _iter_roots() -> list[Path]:
    roots: list[Path] = []
    override = os.environ.get("LOCALVIDEOAI_FFMPEG_DIR")
    if override:
        roots.append(Path(override).expanduser())
    bundled = ffmpeg_dir()
    roots.extend([bundled, bundled / "bin"])
    if bundled.is_dir():
        for child in bundled.iterdir():
            if child.is_dir():
                roots.extend([child, child / "bin"])
    which = shutil.which("ffmpeg")
    if which:
        roots.append(Path(which).resolve().parent)
    try:
        import imageio_ffmpeg

        imageio_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        roots.append(imageio_exe.parent)
    except Exception:
        pass
    return roots


def find_ffmpeg() -> Path:
    seen: set[Path] = set()
    for root in _iter_roots():
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        for name in ("ffmpeg.exe", "ffmpeg"):
            candidate = resolved / name
            if candidate.is_file():
                return candidate
        if resolved.is_file() and resolved.stem == "ffmpeg":
            return resolved
    try:
        import imageio_ffmpeg

        source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError as exc:
        raise MediaError(
            "未找到 FFmpeg。请将 ffmpeg.exe 放到 vendor/ffmpeg/bin/，或安装 imageio-ffmpeg。"
            f" 安装根目录：{install_root()}"
        ) from exc
    if not source.is_file():
        raise MediaError(f"imageio-ffmpeg 未提供可执行文件：{source}")
    dest_dir = ffmpeg_dir() / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "ffmpeg.exe"
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
        return dest
    return source


def find_ffprobe() -> Path:
    ffmpeg = find_ffmpeg()
    name = "ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe"
    probe = ffmpeg.with_name(name)
    if probe.is_file():
        return probe
    raise MediaError(f"找到 FFmpeg 但缺少 ffprobe：{ffmpeg.parent}")


def ffmpeg_available() -> bool:
    try:
        find_ffmpeg()
    except MediaError:
        return False
    return True
