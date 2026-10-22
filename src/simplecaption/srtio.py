"""Write recognized or translated subtitles with the existing SRT renderer."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from localvideoai.subtitles.document import SubtitleDocument


def save_role_srt(document: SubtitleDocument, destination: Path, role: str) -> Path:
    from localvideoai.subtitles.encoding import write_subtitle_text
    from localvideoai.subtitles.srt import render_srt

    clone = deepcopy(document)
    for segment in clone.segments:
        if role == "translated":
            segment.source_text = segment.translated_text.strip() or segment.display_text()
        segment.corrected_text = ""
        segment.translated_text = ""
    write_subtitle_text(destination, render_srt(clone))
    return destination.expanduser().resolve()
