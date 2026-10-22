from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from localvideoai.core.types import SubtitleSegment


@dataclass
class SubtitleDocument:
    segments: list[SubtitleSegment]
    format_name: str
    source_path: Path | None = None
    encoding: str = "utf-8"
    warnings: list[str] = field(default_factory=list)
    script_info: list[str] = field(default_factory=list)
    style_section: str = ""
    events_format: str = ""
    embedded_stream_index: int | None = None
    container_language: str = ""
    detected_language: str = ""
    speaker_map: dict[str, str] = field(default_factory=dict)
    speaker_styles: dict[str, str] = field(default_factory=dict)
    quality_stage: str = ""

    def sorted_copy(self) -> "SubtitleDocument":
        ordered = sorted(
            self.segments,
            key=lambda item: (item.start_time, item.end_time, item.id),
        )
        for index, segment in enumerate(ordered, start=1):
            segment.id = index
        return SubtitleDocument(
            segments=ordered,
            format_name=self.format_name,
            source_path=self.source_path,
            encoding=self.encoding,
            warnings=list(self.warnings),
            script_info=list(self.script_info),
            style_section=self.style_section,
            events_format=self.events_format,
            embedded_stream_index=self.embedded_stream_index,
            container_language=self.container_language,
            detected_language=self.detected_language,
            speaker_map=dict(self.speaker_map),
            speaker_styles=dict(self.speaker_styles),
            quality_stage=self.quality_stage,
        )
