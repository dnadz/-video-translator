"""Locate burned-in subtitle regions from OCR cues or a subtitle document."""

from __future__ import annotations

from localvideoai.core.types import OCRTranscript
from localvideoai.inpaint.types import TimedRegion
from localvideoai.subtitles.document import SubtitleDocument


def regions_from_transcript(transcript: OCRTranscript) -> list[TimedRegion]:
    regions: list[TimedRegion] = []
    for cue in transcript.cues:
        points: list[tuple[float, float]] = []
        for box in cue.boxes:
            points.extend(box.points)
        regions.append(
            TimedRegion(
                start_ms=int(cue.start_ms),
                end_ms=int(max(cue.end_ms, cue.start_ms)),
                text=cue.text,
                x=float(cue.x),
                y=float(cue.y),
                w=float(cue.w or 0.8),
                h=float(cue.h or 0.12),
                points=tuple(points),
            )
        )
    return _sanitize(regions)


def regions_from_document(document: SubtitleDocument) -> list[TimedRegion]:
    regions: list[TimedRegion] = []
    for segment in document.segments:
        extra = segment.extra.get("ocr") if isinstance(segment.extra, dict) else None
        x, y, w, h = 0.08, 0.78, 0.84, 0.16
        if isinstance(extra, dict):
            try:
                x = float(extra.get("x", x))
                y = float(extra.get("y", y))
                w = float(extra.get("w", w))
                h = float(extra.get("h", h))
            except (TypeError, ValueError):
                pass
        text = segment.translated_text.strip() or segment.display_text()
        regions.append(
            TimedRegion(
                start_ms=int(segment.start_time),
                end_ms=int(segment.end_time),
                text=text,
                x=x,
                y=y,
                w=w,
                h=h,
            )
        )
    return _sanitize(regions)


def _sanitize(regions: list[TimedRegion]) -> list[TimedRegion]:
    cleaned: list[TimedRegion] = []
    for item in regions:
        if item.end_ms < item.start_ms:
            continue
        if not (item.text or "").strip():
            continue
        x = min(max(item.x, 0.0), 0.98)
        y = min(max(item.y, 0.0), 0.98)
        w = min(max(item.w, 0.04), 1.0 - x)
        h = min(max(item.h, 0.03), 1.0 - y)
        cleaned.append(
            TimedRegion(
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                text=item.text.strip(),
                x=x,
                y=y,
                w=w,
                h=h,
                points=item.points,
            )
        )
    return cleaned
