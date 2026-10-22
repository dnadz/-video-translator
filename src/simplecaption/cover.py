"""Hide burned-in subtitles with a bottom mosaic, then burn the translation."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from localvideoai.core.exceptions import ExportError
from localvideoai.export.ffmpeg_cmd import escape_filter_path, run_ffmpeg
from localvideoai.media.ffmpeg_runtime import find_ffmpeg

Progress = Callable[[int, int, str], None]


def cover_burned_subtitles(
    video: Path,
    subtitle: Path,
    destination: Path,
    *,
    progress: Progress | None = None,
) -> Path:
    source = video.expanduser().resolve()
    captions = subtitle.expanduser().resolve()
    dest = destination.expanduser().resolve()
    if not source.is_file():
        raise ExportError(f"没有可处理的视频：{source}")
    if not captions.is_file():
        raise ExportError(f"没有可烧录的译文字幕：{captions}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    script = dest.with_suffix(".blur.vf")
    script.write_text(_filter_script(captions), encoding="utf-8")
    duration_ms = _duration_ms(source)
    args = [
        "-i",
        str(source),
        "-/filter_complex",
        str(script),
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-sn",
        *_video_encoder_args(),
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    try:
        run_ffmpeg(args, duration_ms=duration_ms, progress=progress)
    finally:
        script.unlink(missing_ok=True)
    if not dest.is_file() or dest.stat().st_size < 32:
        raise ExportError(f"没有生成去掉原字幕的视频：{dest}")
    return dest


def _filter_script(subtitle: Path) -> str:
    crop = "crop=trunc(iw*96/100/2)*2:trunc(ih*22/100/2)*2:trunc(iw*2/100/2)*2:trunc(ih*76/100/2)*2"
    pixel = "scale=trunc(iw/18/2)*2:trunc(ih/18/2)*2,scale=trunc(iw*18/2)*2:trunc(ih*18/2)*2:flags=neighbor"
    escaped = escape_filter_path(subtitle)
    font = _font_for(subtitle.read_text(encoding="utf-8", errors="replace"))
    style = f"FontName={font},FontSize=22,Alignment=2,MarginV=42,Outline=2,BorderStyle=1"
    return ";".join(
        [
            "[0:v]split[base][band]",
            f"[band]{crop},{pixel}[pix]",
            "[base][pix]overlay=x=trunc(main_w*2/100/2)*2:y=trunc(main_h*76/100/2)*2[covered]",
            f"[covered]subtitles='{escaped}':charenc=UTF-8:force_style='{style}'[vout]",
        ]
    )


def _font_for(text: str) -> str:
    japanese = any("\u3040" <= char <= "\u30ff" for char in text)
    order = (
        ("Yu Gothic", "YuGothM.ttc"),
        ("Meiryo", "meiryo.ttc"),
        ("MS Gothic", "msgothic.ttc"),
        ("Microsoft YaHei", "msyh.ttc"),
    )
    if not japanese:
        order = (order[3], order[0], order[1], order[2])
    fonts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    for family, filename in order:
        if (fonts / filename).is_file():
            return family
    return "Microsoft YaHei"


def _video_encoder_args() -> list[str]:
    try:
        completed = subprocess.run(
            [str(find_ffmpeg()), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        completed = None
    if completed is not None and "h264_nvenc" in (completed.stdout or ""):
        return ["-c:v", "h264_nvenc", "-preset", "p1", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]


def _duration_ms(video: Path) -> int:
    from localvideoai.media.media_analyzer import MediaAnalyzer

    try:
        return max(int(MediaAnalyzer().analyze(video).duration_ms), 0)
    except Exception:
        return 0
