"""Stream sampled RGB frames from FFmpeg. Never dumps every source frame to disk."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from localvideoai.core.exceptions import MediaError
from localvideoai.media.ffmpeg_runtime import find_ffmpeg

DEFAULT_SAMPLE_FPS = 4.0


@dataclass(frozen=True)
class SampledFrame:
    index: int
    time_ms: int
    width: int
    height: int
    rgb: np.ndarray


def iter_sampled_frames(
    media_path: Path,
    width: int,
    height: int,
    duration_ms: int,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
) -> Iterator[SampledFrame]:
    source = media_path.expanduser().resolve()
    if not source.is_file():
        raise MediaError(f"视频不存在：{source}")
    if width <= 0 or height <= 0:
        raise MediaError(f"无法抽帧：分辨率无效 {width}x{height}")
    if sample_fps <= 0:
        raise MediaError("采样帧率必须大于 0")
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
        "-vf",
        f"fps={sample_fps}",
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
        raise MediaError(f"无法启动 FFmpeg 抽帧：{source}") from exc
    if process.stdout is None:
        process.kill()
        raise MediaError(f"FFmpeg 没有提供视频输出：{source}")
    index = 0
    try:
        while True:
            payload = _read_exact(process.stdout, frame_bytes)
            if len(payload) < frame_bytes:
                break
            rgb = np.frombuffer(payload, dtype=np.uint8).reshape((height, width, 3)).copy()
            time_ms = int(round(index * 1000 / sample_fps))
            if duration_ms:
                time_ms = min(time_ms, duration_ms)
            yield SampledFrame(index=index, time_ms=time_ms, width=width, height=height, rgb=rgb)
            index += 1
        return_code = process.wait(timeout=120)
        if index == 0:
            raise MediaError(f"没有读到视频帧：{source}（FFmpeg 退出码 {return_code}）")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def extract_still(media_path: Path, dest: Path, time_ms: int = 1000) -> Path:
    source = media_path.expanduser().resolve()
    dest = dest.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    stamp = max(0, time_ms) / 1000
    command = [
        str(find_ffmpeg()),
        "-hide_banner",
        "-y",
        "-ss",
        f"{stamp:.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        str(dest),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not dest.is_file():
        raise MediaError(f"无法截取预览帧：{source}")
    return dest


def band_signature(rgb: np.ndarray) -> np.ndarray:
    step_y = max(1, rgb.shape[0] // 24)
    step_x = max(1, rgb.shape[1] // 48)
    small = rgb[::step_y, ::step_x]
    if small.ndim == 3:
        small = small.mean(axis=2)
    return small.astype(np.float32)


def signature_changed(previous: np.ndarray | None, current: np.ndarray, threshold: float) -> bool:
    if previous is None or previous.shape != current.shape:
        return True
    return float(np.mean(np.abs(previous - current))) > threshold


def _read_exact(stream, size: int) -> bytes:
    chunks = bytearray()
    remaining = size
    while remaining > 0:
        piece = stream.read(remaining)
        if not piece:
            break
        chunks.extend(piece)
        remaining -= len(piece)
    return bytes(chunks)
