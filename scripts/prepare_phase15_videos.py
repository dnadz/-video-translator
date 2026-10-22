"""Create 10 short legal clips for Phase 15 batch tests. No copyrighted footage."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


def find_cjk_font() -> Path:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    for name in ("msyh.ttc", "msyh.ttf", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"):
        path = root / name
        if path.is_file():
            return path
    raise RuntimeError(f"no CJK font in {root}")


def _font_expr(font: Path) -> str:
    return str(font).replace("\\", "/").replace(":", "\\:")


def _run(ffmpeg: Path, args: list[str]) -> None:
    completed = subprocess.run(
        [str(ffmpeg), "-y", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "")[-4000:])


def write_clip(ffmpeg: Path, font: Path, dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    vf = (
        f"drawtext=fontfile='{_font_expr(font)}':text='{escaped}':fontsize=42:"
        "fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-80:"
        "enable='between(t,0.15,1.05)'"
    )
    script = dest.with_suffix(".vf.txt")
    script.write_text(vf, encoding="utf-8")
    _run(
        ffmpeg,
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1a3a5c:s=640x360:r=25:d=1.2",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=16000:d=1.2",
            "-filter_script:v",
            str(script),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ],
    )
    print(f"{dest} ({dest.stat().st_size} bytes)")


def main() -> int:
    ffmpeg = find_ffmpeg()
    font = find_cjk_font()
    root = ensure_directory(install_root() / "test_assets" / "videos" / "phase15")
    for index in range(1, 11):
        write_clip(ffmpeg, font, root / f"clip_{index:02d}.mp4", f"批量测试{index:02d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
