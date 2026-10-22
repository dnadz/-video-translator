from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from localvideoai.core.types import DiarizationResult, SpeechSegment
from localvideoai.engines.speaker_engine import SpeakerEngine
from localvideoai.speaker.embed import SpeakerEmbedder
from localvideoai.speaker.pipeline import diarize_media, label_document
from localvideoai.speaker.store import is_speaker_model_ready, model_id
from localvideoai.subtitles.document import SubtitleDocument

ProgressCallback = Callable[[int, int, str], None]


class LocalSpeakerEngine(SpeakerEngine):
    """Local embedding + clustering diarization. Falls back to unlabeled subtitles."""

    def __init__(self) -> None:
        self._embedder: SpeakerEmbedder | None = None

    @property
    def engine_id(self) -> str:
        return "onnx-speaker-embedding"

    @property
    def display_name(self) -> str:
        return "Local Speaker Embedding Engine"

    def available(self) -> bool:
        return is_speaker_model_ready()

    def diarize(self, audio_path: Path) -> list[SpeechSegment]:
        return self.diarize_media(audio_path).turns

    def diarize_media(
        self,
        audio_path: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> DiarizationResult:
        return diarize_media(audio_path, embedder=self._embedder_or_none(), progress=progress)

    def label_document(
        self,
        document: SubtitleDocument,
        audio_path: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> DiarizationResult:
        return label_document(
            document,
            audio_path,
            embedder=self._embedder_or_none(),
            progress=progress,
        )

    def _embedder_or_none(self) -> SpeakerEmbedder | None:
        if not is_speaker_model_ready():
            return None
        if self._embedder is None:
            self._embedder = SpeakerEmbedder()
        return self._embedder if self._embedder.available else None


def current_model_id() -> str:
    return model_id()
