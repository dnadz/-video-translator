"""Local hard-subtitle engine. Fast OpenCV first, LaMa ONNX when the model is present."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from localvideoai.core.exceptions import InpaintError
from localvideoai.engines.inpainting_engine import InpaintingEngine
from localvideoai.inpaint.pipeline import process_hard_subtitles
from localvideoai.inpaint.store import is_lama_ready
from localvideoai.inpaint.types import MODE_SMART, InpaintResult
from localvideoai.ocr.region import NormalizedRegion
from localvideoai.subtitles.document import SubtitleDocument

ProgressCallback = Callable[[int, int, str], None]


class LocalInpaintingEngine(InpaintingEngine):
    def __init__(self, ocr_engine=None) -> None:
        self._ocr_engine = ocr_engine

    @property
    def engine_id(self) -> str:
        return "local-hardsub"

    @property
    def display_name(self) -> str:
        return "Local Hard Subtitle Engine"

    def available(self) -> bool:
        return True

    def remove_hard_subs(self, video_path: Path, destination: Path) -> Path:
        return self.process_video(video_path, destination, mode=MODE_SMART).output_path

    def process_video(
        self,
        video_path: Path,
        destination: Path,
        *,
        mode: str = MODE_SMART,
        document: SubtitleDocument | None = None,
        language: str | None = None,
        region: NormalizedRegion | None = None,
        use_ai: bool = True,
        progress: ProgressCallback | None = None,
    ) -> InpaintResult:
        if self._ocr_engine is None:
            from localvideoai.engines import create_ocr_engine

            self._ocr_engine = create_ocr_engine()
        try:
            return process_hard_subtitles(
                video_path,
                destination,
                mode=mode,
                document=document,
                ocr_engine=self._ocr_engine,
                language=language,
                region=region,
                use_ai=use_ai,
                progress=progress,
            )
        except InpaintError:
            raise
        except Exception as exc:
            raise InpaintError(f"硬字幕处理失败：{exc}") from exc

    def ai_ready(self) -> bool:
        return is_lama_ready()
