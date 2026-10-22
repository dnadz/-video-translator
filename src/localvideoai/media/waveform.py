"""Build a compact peak envelope from local media. Does not load the whole PCM file into RAM."""

from __future__ import annotations

import subprocess
from array import array
from dataclasses import dataclass
from pathlib import Path

from localvideoai.core.exceptions import MediaError
from localvideoai.media.ffmpeg_runtime import find_ffmpeg

SAMPLE_RATE = 8000
BYTES_PER_SAMPLE = 2


@dataclass(frozen=True)
class WaveformPeaks:
    peaks: tuple[float, ...]
    duration_ms: int
    hop_ms: int
    sample_rate: int = SAMPLE_RATE
    source: str = ""
    message: str = ""


def extract_waveform_peaks(
    media_path: Path,
    hop_ms: int = 20,
    should_cancel=None,
) -> WaveformPeaks:
    source = media_path.expanduser().resolve()
    if not source.is_file():
        raise MediaError(f"媒体不存在：{source}")
    hop = max(5, int(hop_ms))
    hop_samples = max(1, int(SAMPLE_RATE * hop / 1000))
    command = [
        str(find_ffmpeg()),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vn",
        "-sn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "pipe:1",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = b""
    stderr = b""
    try:
        while True:
            if should_cancel is not None and should_cancel():
                process.kill()
                process.wait(timeout=5)
                raise MediaError("波形提取已取消")
            try:
                stdout, stderr = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
    except Exception:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        raise
    if process.returncode != 0:
        text = (stderr or b"").decode("utf-8", errors="replace")[-1500:]
        raise MediaError(f"无法抽取音频波形：{source}\n{text}")
    raw = stdout or b""
    if len(raw) < BYTES_PER_SAMPLE:
        return WaveformPeaks((), 0, hop, source=str(source), message="没有音轨或音频为空")
    samples = array("h")
    usable = len(raw) - (len(raw) % BYTES_PER_SAMPLE)
    samples.frombytes(raw[:usable])
    peaks: list[float] = []
    for start in range(0, len(samples), hop_samples):
        window = samples[start : start + hop_samples]
        peak = 0
        for value in window:
            magnitude = value if value >= 0 else -value
            if magnitude > peak:
                peak = magnitude
        peaks.append(min(1.0, peak / 32767.0))
    duration_ms = int(round(len(samples) * 1000 / SAMPLE_RATE))
    return WaveformPeaks(tuple(peaks), duration_ms, hop, source=str(source))
