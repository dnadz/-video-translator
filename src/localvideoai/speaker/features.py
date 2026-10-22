"""Kaldi-style log-mel filterbank for 16 kHz speaker embeddings. NumPy only."""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000
N_MELS = 80
FRAME_MS = 25
SHIFT_MS = 10
PREEMPHASIS = 0.97
EPS = 1e-10


def pcm16_to_float(pcm_s16le: bytes) -> np.ndarray:
    if not pcm_s16le:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(pcm_s16le, dtype="<i2")
    return (samples.astype(np.float32) / 32768.0).copy()


def log_mel_fbank(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    wave = np.asarray(samples, dtype=np.float32).reshape(-1)
    if wave.size < 2:
        return np.zeros((1, N_MELS), dtype=np.float32)
    emphasized = np.empty_like(wave)
    emphasized[0] = wave[0]
    emphasized[1:] = wave[1:] - PREEMPHASIS * wave[:-1]
    frame_len = int(sample_rate * FRAME_MS / 1000)
    frame_shift = int(sample_rate * SHIFT_MS / 1000)
    if emphasized.size < frame_len:
        emphasized = np.pad(emphasized, (0, frame_len - emphasized.size))
    n_frames = 1 + (emphasized.size - frame_len) // frame_shift
    window = np.hamming(frame_len).astype(np.float32)
    n_fft = 512
    filters = _mel_filters(sample_rate, n_fft, N_MELS)
    frames = np.lib.stride_tricks.as_strided(
        emphasized,
        shape=(n_frames, frame_len),
        strides=(emphasized.strides[0] * frame_shift, emphasized.strides[0]),
    ).copy()
    frames *= window
    spec = np.abs(np.fft.rfft(frames, n=n_fft)) ** 2
    mel = spec @ filters.T
    log_mel = np.log(np.maximum(mel, EPS)).astype(np.float32)
    log_mel -= log_mel.mean(axis=0, keepdims=True)
    return log_mel


def _mel_filters(sample_rate: int, n_fft: int, n_mels: int) -> np.ndarray:
    n_freqs = n_fft // 2 + 1
    low = 0.0
    high = _hz_to_mel(sample_rate / 2)
    mels = np.linspace(low, high, n_mels + 2)
    hz = _mel_to_hz(mels)
    bins = np.floor((n_fft + 1) * hz / sample_rate).astype(int)
    weights = np.zeros((n_mels, n_freqs), dtype=np.float32)
    for index in range(n_mels):
        left, center, right = bins[index], bins[index + 1], bins[index + 2]
        if center == left:
            center += 1
        if right == center:
            right += 1
        right = min(right, n_freqs - 1)
        for bin_index in range(left, center):
            if 0 <= bin_index < n_freqs:
                weights[index, bin_index] = (bin_index - left) / max(center - left, 1)
        for bin_index in range(center, right):
            if 0 <= bin_index < n_freqs:
                weights[index, bin_index] = (right - bin_index) / max(right - center, 1)
    return weights


def _hz_to_mel(hz: float) -> float:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10 ** (mel / 2595.0) - 1.0)
