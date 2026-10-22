"""Energy VAD for speaker turns. Does not invent speech where energy is silent."""

from __future__ import annotations

import numpy as np

from localvideoai.speaker.features import SAMPLE_RATE


def speech_windows(
    samples: np.ndarray,
    *,
    sample_rate: int = SAMPLE_RATE,
    offset_ms: int = 0,
    frame_ms: int = 30,
    min_on_ms: int = 300,
    min_off_ms: int = 200,
) -> list[tuple[int, int]]:
    wave = np.asarray(samples, dtype=np.float32).reshape(-1)
    if wave.size == 0:
        return []
    frame = max(1, int(sample_rate * frame_ms / 1000))
    energies: list[tuple[int, float]] = []
    for start in range(0, wave.size, frame):
        piece = wave[start : start + frame]
        energies.append((start, float(np.sqrt(np.mean(np.square(piece))))))
    if not energies:
        return []
    values = np.array([item[1] for item in energies], dtype=np.float32)
    threshold = max(0.012, float(np.median(values) * 1.8))
    min_on = max(1, int(min_on_ms / frame_ms))
    min_off = max(1, int(min_off_ms / frame_ms))
    flags = values >= threshold
    ranges: list[tuple[int, int]] = []
    start_index: int | None = None
    off = 0
    for index, spoken in enumerate(flags):
        if spoken:
            if start_index is None:
                start_index = index
            off = 0
            continue
        if start_index is None:
            continue
        off += 1
        if off >= min_off:
            end_index = index - off + 1
            if end_index - start_index >= min_on:
                ranges.append((start_index, end_index))
            start_index = None
            off = 0
    if start_index is not None and len(flags) - start_index >= min_on:
        ranges.append((start_index, len(flags)))
    windows: list[tuple[int, int]] = []
    for start_index, end_index in ranges:
        start_ms = offset_ms + int(energies[start_index][0] * 1000 / sample_rate)
        last = energies[min(end_index, len(energies) - 1)][0] + frame
        end_ms = offset_ms + int(last * 1000 / sample_rate)
        if end_ms - start_ms >= min_on_ms:
            windows.append((start_ms, end_ms))
    return windows
