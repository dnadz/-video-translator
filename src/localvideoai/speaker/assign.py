"""Map diarized turns onto subtitle cues by time overlap."""

from __future__ import annotations

from localvideoai.core.types import SpeechSegment, SubtitleSegment


def overlap_ms(left_start: int, left_end: int, right_start: int, right_end: int) -> int:
    start = max(int(left_start), int(right_start))
    end = min(int(left_end), int(right_end))
    return max(0, end - start)


def majority_speaker(segment: SubtitleSegment, turns: list[SpeechSegment]) -> str:
    scores: dict[str, int] = {}
    for turn in turns:
        speaker = (turn.speaker or "").strip()
        if not speaker:
            continue
        score = overlap_ms(segment.start_time, segment.end_time, turn.start_ms, turn.end_ms)
        if score:
            scores[speaker] = scores.get(speaker, 0) + score
    if not scores:
        return ""
    return max(scores, key=scores.get)
