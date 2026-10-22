"""Run the local speaker-embedding ONNX. UI must not import onnxruntime."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from localvideoai.speaker.features import log_mel_fbank, pcm16_to_float
from localvideoai.speaker.store import embedding_model_path, is_speaker_model_ready, model_id


class SpeakerEmbedder:
    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path or embedding_model_path()
        self.model_id = model_id()
        self.device = "cpu"
        self._session = None
        self._input_name = ""
        if is_speaker_model_ready() or (self.model_path.is_file() and self.model_path.stat().st_size > 1024):
            self._load()

    @property
    def available(self) -> bool:
        return self._session is not None

    def embed_pcm(self, pcm_s16le: bytes) -> np.ndarray | None:
        if self._session is None:
            return None
        samples = pcm16_to_float(pcm_s16le)
        if samples.size < 400:
            return None
        if samples.size < 16000:
            repeats = int(16000 / max(samples.size, 1)) + 1
            samples = np.tile(samples, repeats)[:16000]
        feats = log_mel_fbank(samples)
        if feats.shape[0] < 8:
            pad = np.repeat(feats[-1:], 8 - feats.shape[0], axis=0)
            feats = np.concatenate([feats, pad], axis=0)
        tensor = self._prepare_input(feats)
        outputs = self._session.run(None, {self._input_name: tensor})
        vector = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-8:
            return None
        return vector / norm

    def _load(self) -> None:
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2
        self._session = onnxruntime.InferenceSession(
            str(self.model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        first = self._session.get_inputs()[0]
        self._input_name = first.name
        self._input_rank = len(first.shape)
        self.device = "cpu"

    def _prepare_input(self, feats: np.ndarray) -> np.ndarray:
        data = feats.astype(np.float32)
        if getattr(self, "_input_rank", 3) == 2:
            return data
        return data[np.newaxis, ...]
