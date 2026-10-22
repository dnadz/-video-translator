from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXPORT_MODES = ("sidecar", "burn_in", "embed", "multilingual", "project")
EXPORT_CONTAINERS = ("mp4", "mkv", "webm")
EXPORT_CODECS = ("copy", "h264", "h265")
SUBTITLE_FORMATS = ("srt", "ass", "ssa", "vtt")


@dataclass
class ExportResult:
    output_path: Path
    sidecar_paths: list[Path] = field(default_factory=list)
    mode: str = "sidecar"
    encode_mode: str = "remux"
    container: str = "mp4"
    video_codec: str = ""
    subtitle_tracks: int = 0
    compatibility: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
