"""Generate Phase 2 test videos with the bundled FFmpeg (streamed, not RAM-loaded)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


def _run(ffmpeg: Path, args: list[str]) -> None:
    command = [str(ffmpeg), "-y", *args]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "")[-3000:])


def encode_clip(
    ffmpeg: Path,
    destination: Path,
    *,
    seconds: int,
    width: int,
    height: int,
    container_args: list[str],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ffmpeg,
        [
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={width}x{height}:rate=30:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=44100:duration={seconds}",
            *container_args,
            "-shortest",
            str(destination),
        ],
    )
    if destination.stat().st_size <= 0:
        raise RuntimeError(f"empty video: {destination}")
    print(f"{destination} ({destination.stat().st_size} bytes)")


def main() -> int:
    ffmpeg = find_ffmpeg()
    root = ensure_directory(install_root() / "test_assets" / "videos")
    chinese = ensure_directory(root / "中文路径")
    h264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:v", "1200k"]
    encode_clip(ffmpeg, root / "10秒_测试.mp4", seconds=10, width=1280, height=720, container_args=h264)
    encode_clip(ffmpeg, root / "高分辨率_1080p.mp4", seconds=10, width=1920, height=1080, container_args=h264)
    encode_clip(ffmpeg, root / "10分钟_测试.mp4", seconds=600, width=1280, height=720, container_args=h264)
    encode_clip(ffmpeg, root / "格式测试.mkv", seconds=3, width=640, height=360, container_args=h264)
    encode_clip(ffmpeg, root / "格式测试.mov", seconds=3, width=640, height=360, container_args=h264)
    encode_clip(
        ffmpeg,
        root / "格式测试.avi",
        seconds=3,
        width=640,
        height=360,
        container_args=["-c:v", "mpeg4", "-c:a", "pcm_s16le"],
    )
    try:
        encode_clip(
            ffmpeg,
            root / "格式测试.webm",
            seconds=3,
            width=640,
            height=360,
            container_args=["-c:v", "libvpx", "-b:v", "400k", "-c:a", "libvorbis"],
        )
    except RuntimeError as exc:
        print(f"webm skipped: {exc}")
        encode_clip(ffmpeg, root / "格式测试.webm", seconds=3, width=640, height=360, container_args=h264 + ["-f", "webm"])
    for name in ("10秒_测试.mp4", "高分辨率_1080p.mp4"):
        source = root / name
        target = chinese / name
        target.write_bytes(source.read_bytes())
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
