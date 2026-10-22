from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from localvideoai.core.types import ExportRequest
from localvideoai.engines.base import BaseEngine


class ExportEngine(BaseEngine):
    """Mux subtitles and export video locally via FFmpeg."""

    @abstractmethod
    def export(self, request: ExportRequest) -> Path:
        """Write the export to request.output_path. Must not upload media."""
