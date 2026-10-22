from __future__ import annotations

from pathlib import Path

from localvideoai.core.exceptions import SubtitleError

_STRICT = ("utf-8-sig", "utf-8")
_FALLBACK = ("shift_jis", "cp932", "gb18030", "big5", "utf-16")


def read_subtitle_text(path: Path) -> tuple[str, str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SubtitleError(f"无法读取字幕文件：{path}") from exc
    if not data:
        raise SubtitleError(f"字幕文件为空：{path}")
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16-le"), "utf-16-le"
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16-be"), "utf-16-be"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    for encoding in _STRICT:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    ranked: list[tuple[int, str, str]] = []
    for encoding in _FALLBACK:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        ranked.append((_encoding_score(text), encoding, text))
    if not ranked:
        raise SubtitleError(f"无法识别字幕编码：{path}")
    ranked.sort(key=lambda item: item[0], reverse=True)
    _score, encoding, text = ranked[0]
    return text, encoding


def write_subtitle_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text if text.endswith("\n") else text + "\n"
    try:
        path.write_text(payload, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise SubtitleError(f"无法保存字幕文件：{path}") from exc


def _encoding_score(text: str) -> int:
    score = 0
    for char in text:
        code = ord(char)
        if char == "\ufffd":
            score -= 200
        elif 0x3040 <= code <= 0x30FF:
            score += 8
        elif 0x4E00 <= code <= 0x9FFF:
            score += 2
        elif 0xFF00 <= code <= 0xFFEF:
            score += 2
        elif code < 32 and char not in "\n\r\t":
            score -= 8
        elif code == 0:
            score -= 50
    return score
