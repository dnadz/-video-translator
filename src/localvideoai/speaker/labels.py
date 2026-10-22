"""Canonical Speaker 1/2/3 ids, user-facing names, and per-speaker styles."""

from __future__ import annotations

from localvideoai.subtitles.document import SubtitleDocument

SPEAKER_STYLE_TABLE = (
    ("Speaker1", "&H0000E5FF"),
    ("Speaker2", "&H0066FFB4"),
    ("Speaker3", "&H004B9BFF"),
    ("Speaker4", "&H00C17DFF"),
    ("Speaker5", "&H00FF6EC7"),
    ("Speaker6", "&H006ED4FF"),
    ("Speaker7", "&H007DFF7A"),
    ("Speaker8", "&H00A0A0A0"),
)

_ASS_STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)


def speaker_id(index: int) -> str:
    return f"Speaker {int(index) + 1}"


def default_style_id(canonical: str) -> str:
    number = _speaker_number(canonical)
    if number <= 0:
        return "Default"
    name, _color = SPEAKER_STYLE_TABLE[(number - 1) % len(SPEAKER_STYLE_TABLE)]
    return name


def display_name(document: SubtitleDocument, canonical: str) -> str:
    return (document.speaker_map.get(canonical) or canonical).strip() or canonical


def apply_speaker_rename(
    document: SubtitleDocument,
    canonical: str,
    name: str,
    style_id: str | None = None,
) -> None:
    label = (name or "").strip() or canonical
    document.speaker_map[canonical] = label
    chosen_style = (style_id or document.speaker_styles.get(canonical) or default_style_id(canonical)).strip()
    document.speaker_styles[canonical] = chosen_style
    document.speaker_styles[label] = chosen_style
    for segment in document.segments:
        current_id = str(segment.extra.get("speaker_id") or "")
        if current_id == canonical or segment.speaker == canonical:
            segment.extra["speaker_id"] = canonical
            segment.speaker = label
            segment.style_id = chosen_style
    ensure_speaker_styles(document)


def assign_canonical(document: SubtitleDocument, segment_index: int, canonical: str) -> None:
    segment = document.segments[segment_index]
    segment.extra["speaker_id"] = canonical
    segment.speaker = display_name(document, canonical)
    segment.style_id = document.speaker_styles.get(canonical) or default_style_id(canonical)
    document.speaker_styles.setdefault(canonical, segment.style_id)


def ensure_speaker_styles(document: SubtitleDocument) -> None:
    used = {segment.style_id for segment in document.segments if segment.style_id}
    used.update(default_style_id(f"Speaker {index}") for index in range(1, 4))
    lines = [line for line in (document.style_section or "").splitlines() if line.strip()]
    if not any(line.lower().startswith("format:") for line in lines):
        lines = [_ASS_STYLE_FORMAT, *lines]
    existing = { _style_name(line) for line in lines if line.lower().startswith("style:") }
    for style_name, color in SPEAKER_STYLE_TABLE:
        if style_name in used and style_name not in existing:
            lines.append(_ass_style_line(style_name, color))
            existing.add(style_name)
    document.style_section = "\n".join(lines).strip()


def _speaker_number(canonical: str) -> int:
    text = (canonical or "").strip()
    if text.lower().startswith("speaker"):
        tail = text.split()[-1]
        if tail.isdigit():
            return int(tail)
    return 0


def _style_name(line: str) -> str:
    payload = line.split(":", 1)[-1].strip()
    return payload.split(",", 1)[0].strip()


def _ass_style_line(name: str, primary: str) -> str:
    return (
        f"Style: {name},Arial,48,{primary},&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1"
    )
