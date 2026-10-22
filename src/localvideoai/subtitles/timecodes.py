from __future__ import annotations

from localvideoai.core.exceptions import SubtitleError


def parse_timestamp(value: str, *, centiseconds: bool = False) -> int:
    text = (value or "").strip()
    if not text:
        raise SubtitleError("时间戳为空")
    text = text.replace(",", ".")
    parts = text.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, rest = parts
        elif len(parts) == 2:
            hours = "0"
            minutes, rest = parts
        else:
            raise ValueError
        if "." in rest:
            seconds, fraction = rest.split(".", 1)
        else:
            seconds, fraction = rest, "0"
        hours_i = int(hours)
        minutes_i = int(minutes)
        seconds_i = int(seconds)
        if minutes_i > 59 or seconds_i > 59 or hours_i < 0:
            raise ValueError
        if centiseconds:
            cs = int(fraction.ljust(2, "0")[:2])
            millis = cs * 10
        else:
            millis = int(fraction.ljust(3, "0")[:3])
    except ValueError as exc:
        raise SubtitleError(f"无法解析时间戳：{value}") from exc
    return ((hours_i * 60 + minutes_i) * 60 + seconds_i) * 1000 + millis


def format_srt_timestamp(ms: int) -> str:
    hours, minutes, seconds, millis = _split_ms(ms)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def format_vtt_timestamp(ms: int) -> str:
    hours, minutes, seconds, millis = _split_ms(ms)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def format_ass_timestamp(ms: int) -> str:
    hours, minutes, seconds, millis = _split_ms(ms)
    centiseconds = (millis + 5) // 10
    if centiseconds >= 100:
        seconds += 1
        centiseconds = 0
        if seconds >= 60:
            seconds = 0
            minutes += 1
            if minutes >= 60:
                minutes = 0
                hours += 1
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _split_ms(ms: int) -> tuple[int, int, int, int]:
    total = max(0, int(ms))
    millis = total % 1000
    total //= 1000
    seconds = total % 60
    total //= 60
    minutes = total % 60
    hours = total // 60
    return hours, minutes, seconds, millis
