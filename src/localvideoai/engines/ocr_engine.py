from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from pathlib import Path

from localvideoai.core.types import OCRBox, OCRTranscript
from localvideoai.engines.base import BaseEngine
from localvideoai.ocr.region import NormalizedRegion

ProgressCallback = Callable[[int, int, str], None]


class OCREngine(BaseEngine):
    """Local OCR for hard subtitles and on-screen text."""

    @abstractmethod
    def recognize_image(self, image_path: Path) -> list[OCRBox]:
        """OCR a local image. Must not upload the image."""

    @abstractmethod
    def recognize_video(
        self,
        video_path: Path,
        language: str | None = None,
        *,
        region: NormalizedRegion | tuple[float, float, float, float] | None = None,
        device_preference: str = "auto",
        prefer_gpu: bool = True,
        sample_fps: float = 4.0,
        save_raw: bool = True,
        raw_path: Path | None = None,
        progress: ProgressCallback | None = None,
    ) -> OCRTranscript:
        """OCR burned-in subtitles. Must sample frames; must not upload the video."""
