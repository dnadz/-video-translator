"""Burn legal hard-subtitle test videos with FFmpeg drawtext. No copyrighted footage."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


def find_cjk_font() -> Path:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    for name in ("msyh.ttc", "msyh.ttf", "msyhbd.ttc", "simhei.ttf", "simsun.ttc", "YuGothM.ttc"):
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


def _draw(font: Path, text: str, y: str, enable: str, size: int = 42) -> str:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return (
        f"drawtext=fontfile='{_font_expr(font)}':text='{escaped}':fontsize={size}:"
        f"fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y={y}:enable='{enable}'"
    )


def _render(ffmpeg: Path, dest: Path, duration: float, vf: str, color: str = "0x1b2434") -> None:
    script = dest.with_suffix(".vf.txt")
    script.write_text(vf, encoding="utf-8")
    _run(
        ffmpeg,
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1280x720:d={duration}:r=25",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=mono:sample_rate=16000:d={duration}",
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


def _scene_cut(ffmpeg: Path, dest: Path, font: Path) -> None:
    script = dest.with_suffix(".vf.txt")
    vf = (
        "[0][1]concat=n=2:v=1:a=0,"
        + _draw(font, "场景切换仍有字幕", "h-90", "gte(t,0.3)")
        + "[v]"
    )
    script.write_text(vf, encoding="utf-8")
    _run(
        ffmpeg,
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=0x203050:s=1280x720:d=4:r=25",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x603020:s=1280x720:d=4:r=25",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=16000:d=8",
            "-filter_complex_script",
            str(script),
            "-map",
            "[v]",
            "-map",
            "2:a",
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
    root = ensure_directory(install_root() / "test_assets" / "videos" / "phase7")
    print(f"font: {font}")
    _render(
        ffmpeg,
        root / "zh_static.mp4",
        8,
        _draw(font, "这是硬字幕测试", "h-90", "between(t,1,7)"),
    )
    _render(
        ffmpeg,
        root / "zh_dynamic.mp4",
        8,
        ",".join(
            [
                _draw(font, "第一句变化", "h-90", "between(t,0.4,2.0)"),
                _draw(font, "第二句出现", "h-90", "between(t,2.0,3.8)"),
                _draw(font, "第三句切换", "h-90", "between(t,3.8,6.8)"),
            ]
        ),
    )
    _render(
        ffmpeg,
        root / "zh_twoline.mp4",
        8,
        ",".join(
            [
                _draw(font, "第一行中文字幕", "h-130", "between(t,1,7)", 40),
                _draw(font, "第二行继续测试", "h-78", "between(t,1,7)", 40),
            ]
        ),
    )
    _render(
        ffmpeg,
        root / "en_static.mp4",
        8,
        _draw(font, "Hard subtitle test", "h-90", "between(t,1,7)"),
    )
    _render(
        ffmpeg,
        root / "en_dynamic.mp4",
        8,
        ",".join(
            [
                _draw(font, "First English line", "h-90", "between(t,0.5,2.4)"),
                _draw(font, "Second English line", "h-90", "between(t,2.4,4.6)"),
                _draw(font, "Third English line", "h-90", "between(t,4.6,7.0)"),
            ]
        ),
    )
    _render(
        ffmpeg,
        root / "ja_static.mp4",
        8,
        _draw(font, "本日は晴天なり", "h-90", "between(t,1,7)"),
    )
    _render(
        ffmpeg,
        root / "blank.mp4",
        4,
        "null",
        color="0x101018",
    )
    chinese_dir = ensure_directory(root / "中文路径")
    _render(
        ffmpeg,
        chinese_dir / "日英混合.mp4",
        6,
        _draw(font, "日本語テスト", "h-90", "between(t,0.8,5)"),
    )
    _scene_cut(ffmpeg, root / "zh_scene.mp4", font)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
