"""Create 10-minute / 1-hour / 2-hour videos for Phase 19 performance tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


CLIPS = (
    ("10分钟_性能.mp4", 600, "10min.mp3"),
    ("1小时_性能.mp4", 3600, "1hour.mp3"),
    ("2小时_性能.mp4", 7200, "2hour.mp3"),
)


def _run(ffmpeg: Path, args: list[str]) -> None:
    command = [str(ffmpeg), "-y", "-hide_banner", *args]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "")[-3000:])


def encode_long_video(ffmpeg: Path, destination: Path, seconds: int, audio: Path | None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-f",
        "lavfi",
        "-i",
        f"color=c=navy:s=320x180:r=1:d={seconds}",
    ]
    if audio is not None and audio.is_file():
        args.extend(["-i", str(audio), "-c:a", "copy"])
    else:
        args.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:sample_rate=16000:duration={seconds}",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
            ]
        )
    args.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            str(destination),
        ]
    )
    _run(ffmpeg, args)
    if not destination.is_file() or destination.stat().st_size < 1024:
        raise RuntimeError(f"empty video: {destination}")
    print(f"{destination} ({destination.stat().st_size} bytes)")
    return destination


def prepare_phase19_videos(root: Path | None = None) -> dict[str, Path]:
    ffmpeg = find_ffmpeg()
    dest_dir = ensure_directory((root or install_root()) / "test_assets" / "videos" / "phase19")
    audio_dir = install_root() / "test_assets" / "audio" / "phase6"
    written: dict[str, Path] = {}
    for name, seconds, audio_name in CLIPS:
        dest = dest_dir / name
        if dest.is_file() and dest.stat().st_size > 1024:
            print(f"exists {dest} ({dest.stat().st_size} bytes)")
            written[name] = dest
            continue
        written[name] = encode_long_video(ffmpeg, dest, seconds, audio_dir / audio_name)
    return written


def main() -> int:
    prepare_phase19_videos()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
