"""Build and run local FFmpeg export commands. Progress comes from real time= lines."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from localvideoai.core.exceptions import ExportError
from localvideoai.export.planner import ExportPlan
from localvideoai.media.ffmpeg_runtime import find_ffmpeg

Progress = Callable[[int, int, str], None]
_TIME = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def escape_filter_path(path: Path) -> str:
    text = path.resolve().as_posix().replace(":", "\\:")
    return text.replace("'", "\\'")


def find_cjk_font() -> Path | None:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
    for name in ("msyh.ttc", "msyh.ttf", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def video_encoder_args(codec: str) -> list[str]:
    if codec == "copy":
        return ["-c:v", "copy"]
    if codec == "h265":
        return ["-c:v", "libx265", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
    if codec == "vp9":
        return ["-c:v", "libvpx-vp9", "-b:v", "1M", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]


def audio_encoder_args(codec: str) -> list[str]:
    if not codec:
        return ["-an"]
    if codec == "copy":
        return ["-c:a", "copy"]
    if codec == "libopus":
        return ["-c:a", "libopus", "-b:a", "96k"]
    return ["-c:a", "aac", "-b:a", "128k"]


def run_ffmpeg(
    args: list[str],
    *,
    duration_ms: int = 0,
    progress: Progress | None = None,
) -> None:
    command = [str(find_ffmpeg()), "-y", "-hide_banner", *args]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_chunks: list[str] = []
    assert process.stderr is not None
    for line in process.stderr:
        stderr_chunks.append(line)
        match = _TIME.search(line)
        if match and progress:
            hours, minutes, seconds = match.groups()
            current = int((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
            total = max(duration_ms, current, 1)
            progress(min(current, total), total, line.strip())
    code = process.wait()
    if process.stdout is not None:
        process.stdout.read()
    if code != 0:
        raise ExportError(f"FFmpeg 导出失败：{''.join(stderr_chunks)[-3000:]}")


def remux_or_encode(
    video: Path,
    destination: Path,
    plan: ExportPlan,
    subtitle_files: list[tuple[Path, str, str]],
    *,
    burn_file: Path | None = None,
    duration_ms: int = 0,
    progress: Progress | None = None,
    work_dir: Path | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    args: list[str] = ["-i", str(video)]
    for path, _, _ in subtitle_files:
        args.extend(["-i", str(path)])
    if burn_file is not None:
        script = _burn_filter_script(burn_file, work_dir or destination.parent)
        args.extend(["-filter_script:v", str(script)])
        args.extend(["-map", "0:v:0", "-map", "0:a?"])
    else:
        args.extend(["-map", "0:v:0", "-map", "0:a?"])
        for index in range(len(subtitle_files)):
            args.extend(["-map", f"{index + 1}:0"])
    args.extend(video_encoder_args(plan.video_codec))
    args.extend(audio_encoder_args(plan.audio_codec))
    if subtitle_files and plan.subtitle_codec:
        args.extend(["-c:s", plan.subtitle_codec])
        for index, (_, language, title) in enumerate(subtitle_files):
            args.extend([f"-metadata:s:s:{index}", f"language={language}"])
            if title:
                args.extend([f"-metadata:s:s:{index}", f"title={title}"])
    if plan.container == "mp4":
        args.extend(["-movflags", "+faststart"])
    args.append(str(destination))
    run_ffmpeg(args, duration_ms=duration_ms, progress=progress)
    if not destination.is_file() or destination.stat().st_size < 32:
        raise ExportError(f"导出没有写出有效文件：{destination}")


def _burn_filter_script(subtitle: Path, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    font = find_cjk_font()
    escaped = escape_filter_path(subtitle)
    extra = ""
    if font is not None:
        extra = f":fontsdir='{escape_filter_path(font.parent)}':force_style='FontName=Microsoft YaHei,FontSize=22'"
    script = work_dir / "burn_subtitles.vf"
    script.write_text(f"subtitles='{escaped}'{extra}", encoding="utf-8")
    return script
