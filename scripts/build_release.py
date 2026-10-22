"""Build LocalVideoAI.exe, LocalVideoAI_Setup.exe, and LocalVideoAI_Portable.exe."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg
from localvideoai.release.sfx import build_setup_and_portable


def run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {command}")


def copy_tree(source: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)


def stage_app(root: Path, staged: Path) -> Path:
    dist = root / "dist" / "LocalVideoAI"
    if not (dist / "LocalVideoAI.exe").is_file():
        raise RuntimeError(f"missing PyInstaller output: {dist / 'LocalVideoAI.exe'}")
    copy_tree(dist, staged)
    for relative in ("config", "vendor/ffmpeg"):
        source = root / relative
        if source.exists():
            target = staged / relative
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
    samples = staged / "samples"
    samples.mkdir(exist_ok=True)
    sample = root / "test_assets" / "videos" / "10秒_测试.mp4"
    if sample.is_file():
        shutil.copy2(sample, samples / "sample.mp4")
    (staged / "PORTABLE_README.txt").write_text(
        (root / "packaging" / "PORTABLE_README.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ffmpeg = staged / "vendor" / "ffmpeg"
    if not any(ffmpeg.rglob("ffmpeg.exe")):
        bundled = Path(find_ffmpeg())
        dest = ffmpeg / "bin"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, dest / "ffmpeg.exe")
    return staged


def find_iscc(root: Path) -> Path | None:
    for candidate in (
        Path(os.environ.get("LOCALVIDEOAI_ISCC", "")),
        root / "vendor" / "innosetup" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ):
        if candidate and candidate.is_file():
            return candidate
    return None


def write_portable_flag(folder: Path) -> None:
    (folder / "portable.flag").write_text("1\n", encoding="utf-8")


def zip_portable(folder: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in folder.rglob("*"):
            if file.is_file():
                archive.write(file, file.relative_to(folder.parent))


def main() -> int:
    root = install_root()
    python = Path(os.environ.get("VIRTUAL_ENV", root / ".venv")) / "Scripts" / "python.exe"
    if not python.is_file():
        python = Path(sys.executable)
    skip_pyinstaller = "--skip-pyinstaller" in sys.argv
    dist_exe = root / "dist" / "LocalVideoAI" / "LocalVideoAI.exe"
    if not skip_pyinstaller or not dist_exe.is_file():
        run([str(python), "-m", "pip", "install", "pyinstaller>=6.3"])
        spec = root / "packaging" / "localvideoai.spec"
        run([str(python), "-m", "PyInstaller", "--noconfirm", "--clean", str(spec)], cwd=root)
    release = root / "release"
    if release.exists():
        shutil.rmtree(release)
    release.mkdir()
    app = stage_app(root, release / "app")
    portable = release / "LocalVideoAI"
    copy_tree(app, portable)
    write_portable_flag(portable)
    zip_portable(portable, release / "LocalVideoAI_Portable.zip")
    iscc = find_iscc(root)
    if iscc and "--native-sfx" not in sys.argv:
        run([str(iscc), str(root / "packaging" / "LocalVideoAI.iss")])
        run([str(iscc), str(root / "packaging" / "LocalVideoAI_Portable.iss")])
        print("built with Inno Setup")
    else:
        built = build_setup_and_portable(root, app, release)
        print("built with native SFX (Inno Setup not present)")
        for key, path in built.items():
            print(f"  {key}: {path} size={path.stat().st_size}")
    print(f"release {__version__}")
    app_exe = app / "LocalVideoAI.exe"
    print(f"{app_exe} exists={app_exe.is_file()} size={app_exe.stat().st_size if app_exe.is_file() else 0}")
    if not app_exe.is_file():
        raise RuntimeError(f"missing application exe: {app_exe}")
    for name in ("LocalVideoAI_Setup.exe", "LocalVideoAI_Portable.exe", "LocalVideoAI_Portable.zip"):
        path = release / name
        print(f"{path} exists={path.is_file()} size={path.stat().st_size if path.is_file() else 0}")
        if name.endswith(".exe") and not path.is_file():
            raise RuntimeError(f"missing release artifact: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
