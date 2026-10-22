"""Build release/SimpleCaption/SimpleCaption.exe without touching LocalVideoAI."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "simplecaption.spec"
DIST = ROOT / "dist" / "SimpleCaption"
RELEASE = ROOT / "release" / "SimpleCaption"


def main() -> int:
    python = Path(sys.executable)
    subprocess.run(
        [str(python), "-m", "PyInstaller", "--noconfirm", "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build" / "simplecaption"), str(SPEC)],
        cwd=ROOT,
        check=True,
    )
    exe = DIST / "SimpleCaption.exe"
    if not exe.is_file():
        raise SystemExit(f"missing {exe}")
    destination = RELEASE
    try:
        if RELEASE.exists():
            shutil.rmtree(RELEASE)
    except OSError:
        destination = ROOT / "release" / "SimpleCaption2"
        if destination.exists():
            shutil.rmtree(destination)
    shutil.copytree(DIST, destination)
    print(destination / "SimpleCaption.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
