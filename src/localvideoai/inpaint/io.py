"""Decode/encode full videos as RGB frames. This writes a real video file."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from localvideoai.core.exceptions import InpaintError
from localvideoai.media.ffmpeg_runtime import find_ffmpeg
from localvideoai.ocr.sampler import _read_exact


def iter_native_frames(path: Path, width: int, height: int) -> Iterator[np.ndarray]:
    source = path.expanduser().resolve()
    frame_bytes = width * height * 3
    command = [
        str(find_ffmpeg()),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-an",
        "-sn",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise InpaintError(f"无法解码视频：{source}") from exc
    if process.stdout is None:
        process.kill()
        raise InpaintError(f"FFmpeg 没有视频输出：{source}")
    try:
        while True:
            payload = _read_exact(process.stdout, frame_bytes)
            if len(payload) < frame_bytes:
                break
            yield np.frombuffer(payload, dtype=np.uint8).reshape((height, width, 3)).copy()
        process.wait(timeout=120)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def copy_video(source: Path, destination: Path) -> Path:
    dest = destination.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(find_ffmpeg()),
        "-y",
        "-hide_banner",
        "-i",
        str(source.expanduser().resolve()),
        "-c",
        "copy",
        str(dest),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not dest.is_file() or dest.stat().st_size < 32:
        command = [
            str(find_ffmpeg()),
            "-y",
            "-hide_banner",
            "-i",
            str(source.expanduser().resolve()),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(dest),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0 or not dest.is_file():
            raise InpaintError(f"无法复制视频：{source}\n{(completed.stderr or '')[-2000:]}")
    return dest


class FrameWriter:
    def __init__(self, source: Path, destination: Path, width: int, height: int, fps: float) -> None:
        dest = destination.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.destination = dest
        rate = f"{fps:.3f}" if fps else "25"
        command = [
            str(find_ffmpeg()),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            rate,
            "-i",
            "pipe:0",
            "-i",
            str(source.expanduser().resolve()),
            "-map",
            "0:v:0",
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise InpaintError(f"无法启动视频编码：{dest}") from exc
        if self._process.stdin is None:
            self._process.kill()
            raise InpaintError(f"编码器没有输入管道：{dest}")

    def write(self, rgb: np.ndarray) -> None:
        if self._process.stdin is None:
            raise InpaintError("编码器已关闭")
        self._process.stdin.write(np.ascontiguousarray(rgb, dtype=np.uint8).tobytes())

    def close(self) -> Path:
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except OSError:
                pass
        stderr = ""
        if self._process.stderr is not None:
            stderr = self._process.stderr.read().decode("utf-8", errors="replace")
        code = self._process.wait(timeout=180)
        if code != 0 or not self.destination.is_file() or self.destination.stat().st_size < 32:
            raise InpaintError(f"写出处理后视频失败：{self.destination}\n{stderr[-2000:]}")
        return self.destination
