"""Create short legal hard-subtitle fixtures for Phase 14. No copyrighted footage."""

from __future__ import annotations

import subprocess
from pathlib import Path

import os

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


def _draw(font: Path, text: str, y: str, enable: str, size: int = 42) -> str:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return (
        f"drawtext=fontfile='{_font_expr(font)}':text='{escaped}':fontsize={size}:"
        f"fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y={y}:enable='{enable}'"
    )


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


def _write(ffmpeg: Path, dest: Path, video_src: list[str], vf: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    script = dest.with_suffix(".vf.txt")
    script.write_text(vf, encoding="utf-8")
    _run(
        ffmpeg,
        [
            *video_src,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=16000:d=3",
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
    root = ensure_directory(install_root() / "test_assets" / "videos" / "phase14")
    caption = _draw(font, "硬字幕测试", "h-90", "between(t,0.3,2.8)", 42)
    _write(
        ffmpeg,
        root / "solid.mp4",
        ["-f", "lavfi", "-i", "color=c=0x2a6b3c:s=1280x720:d=3:r=25"],
        caption,
    )
    _write(
        ffmpeg,
        root / "complex.mp4",
        ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=3"],
        caption,
    )
    person_text = _draw(font, "人物后方字幕", "h-90", "between(t,0.3,2.8)", 42)
    _write(
        ffmpeg,
        root / "person.mp4",
        ["-f", "lavfi", "-i", "color=c=0x1a2744:s=1280x720:d=3:r=25"],
        "drawbox=x=520:y=430:w=240:h=250:color=0xdb8a67:t=fill,"
        "drawbox=x=575:y=330:w=130:h=130:color=0xf0c0a0:t=fill,"
        + person_text,
    )
    moving = _draw(font, "动态背景字幕", "h-90", "between(t,0.3,2.8)", 42)
    _write(
        ffmpeg,
        root / "dynamic.mp4",
        ["-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=3"],
        "hue=h=t*80," + moving,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
