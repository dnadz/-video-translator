"""Copy a real ffmpeg.exe into vendor/ffmpeg/bin so users do not install FFmpeg."""

from __future__ import annotations

import shutil
from pathlib import Path

from localvideoai.core.paths import ensure_directory, ffmpeg_dir


def main() -> int:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise SystemExit("pip install imageio-ffmpeg 后再运行此脚本") from exc
    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not source.is_file():
        raise SystemExit(f"imageio-ffmpeg 未提供 ffmpeg.exe: {source}")
    dest_dir = ensure_directory(ffmpeg_dir() / "bin")
    dest = dest_dir / "ffmpeg.exe"
    shutil.copy2(source, dest)
    print(dest)
    print(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
