"""Write subtitle files for export. Reuses existing SRT/ASS/SSA/VTT renderers."""

from __future__ import annotations

from pathlib import Path

from localvideoai.core.exceptions import ExportError
from localvideoai.core.types import ExportLanguageTrack, ExportRequest, SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import SUPPORTED_FORMATS, load_subtitle, save_subtitle

LANGUAGE_CODES = {
    "zh": "chi",
    "zh-cn": "chi",
    "zh-tw": "chi",
    "chi": "chi",
    "en": "eng",
    "en-us": "eng",
    "eng": "eng",
    "ja": "jpn",
    "ja-jp": "jpn",
    "jpn": "jpn",
}


def normalize_language(code: str) -> str:
    key = (code or "").strip().lower()
    return LANGUAGE_CODES.get(key, key[:3] if key else "und")


def document_with_role(document: SubtitleDocument, role: str) -> SubtitleDocument:
    clone = document.sorted_copy()
    for segment in clone.segments:
        segment.source_text = _text_for_role(segment, role)
        segment.corrected_text = ""
    return clone


def _text_for_role(segment: SubtitleSegment, role: str) -> str:
    if role == "translated":
        return segment.translated_text.strip() or segment.display_text()
    if role == "source":
        return segment.source_text
    return segment.display_text()


def load_document(path: Path | None, fallback: SubtitleDocument | None = None) -> SubtitleDocument:
    if path is not None and path.is_file():
        return load_subtitle(path)
    if fallback is not None:
        return fallback
    raise ExportError("没有可导出的字幕")


def write_subtitle_file(document: SubtitleDocument, destination: Path, fmt: str) -> Path:
    chosen = (fmt or destination.suffix.lstrip(".") or "srt").lower()
    if chosen not in SUPPORTED_FORMATS:
        raise ExportError(f"不支持的字幕格式：{chosen}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return save_subtitle(document, destination.with_suffix(f".{chosen}"), chosen)


def build_tracks(
    request: ExportRequest,
    document: SubtitleDocument | None,
) -> list[tuple[ExportLanguageTrack, SubtitleDocument]]:
    tracks: list[tuple[ExportLanguageTrack, SubtitleDocument]] = []
    if request.tracks:
        for spec in request.tracks:
            source = load_document(spec.subtitle_path, document)
            tracks.append((spec, document_with_role(source, spec.text_role)))
        return tracks
    if document is None and request.subtitle_path:
        document = load_subtitle(request.subtitle_path)
    if document is None:
        return []
    primary_lang = document.detected_language or document.container_language or "zh"
    has_translation = any(item.translated_text.strip() for item in document.segments)
    if request.mode in {"embed", "burn_in"} and has_translation:
        translated = " ".join(item.translated_text for item in document.segments)
        language = "chi" if any("\u4e00" <= char <= "\u9fff" for char in translated) else (
            "eng" if normalize_language(primary_lang) == "chi" else "chi"
        )
        tracks.append(
            (
                ExportLanguageTrack(language=language, title="中文字幕" if language == "chi" else "译文", text_role="translated"),
                document_with_role(document, "translated"),
            )
        )
        return tracks
    tracks.append(
        (
            ExportLanguageTrack(language=normalize_language(primary_lang), title="原文", text_role="display"),
            document_with_role(document, "display"),
        )
    )
    if request.mode in {"multilingual", "project"} and has_translation:
        tracks.append(
            (
                ExportLanguageTrack(language="eng" if normalize_language(primary_lang) == "chi" else "chi", title="译文", text_role="translated"),
                document_with_role(document, "translated"),
            )
        )
    return tracks


def write_sidecars(
    tracks: list[tuple[ExportLanguageTrack, SubtitleDocument]],
    stem: Path,
    fmt: str,
) -> list[Path]:
    written: list[Path] = []
    if not tracks:
        return written
    if len(tracks) == 1:
        written.append(write_subtitle_file(tracks[0][1], stem.with_suffix(f".{fmt}"), fmt))
        return written
    for spec, doc in tracks:
        suffix = spec.language or "und"
        written.append(write_subtitle_file(doc, stem.with_name(f"{stem.stem}.{suffix}.{fmt}"), fmt))
    return written
