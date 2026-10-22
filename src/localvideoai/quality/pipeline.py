"""Recognition → correction → translation review → QA → confirm → lock."""

from __future__ import annotations

from localvideoai.core.types import SubtitleCue, SubtitleSegment
from localvideoai.quality.checks import document_term_consistency, inspect_segment
from localvideoai.quality.correct import correct_subtitle_text
from localvideoai.quality.metrics import cps_of, recognition_score, translation_score
from localvideoai.quality.types import CueQuality, QualityReport, band_for, clamp_score
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.resources import TranslationResources


def expect_translation(document: SubtitleDocument) -> bool:
    return any(item.translated_text.strip() for item in document.segments)


def apply_correction(document: SubtitleDocument) -> int:
    changed = 0
    for segment in document.segments:
        if segment.locked:
            continue
        source = segment.display_text()
        fixed = correct_subtitle_text(source)
        if fixed == source.strip():
            continue
        segment.corrected_text = fixed
        changed += 1
    return changed


def confirm_cue(document: SubtitleDocument, index: int) -> None:
    segment = document.segments[index]
    payload = dict(segment.extra.get("qa") or {})
    payload["confirmed"] = True
    payload["stage"] = "confirm"
    segment.extra["qa"] = payload
    if all(_confirmed_or_locked(item) for item in document.segments):
        document.quality_stage = "confirm"


def lock_confirmed(document: SubtitleDocument) -> int:
    locked = 0
    for segment in document.segments:
        qa = segment.extra.get("qa") if isinstance(segment.extra, dict) else {}
        if isinstance(qa, dict) and qa.get("confirmed") and not segment.locked:
            segment.locked = True
            locked += 1
    if locked:
        document.quality_stage = "lock"
    return locked


def inspect_document(
    document: SubtitleDocument,
    *,
    resources: TranslationResources | None = None,
    apply_fixes: bool = False,
) -> QualityReport:
    if not document.segments:
        document.quality_stage = document.quality_stage or "qa"
        return QualityReport(cues=[], stage=document.quality_stage, document_score=100.0, issue_count=0)
    if apply_fixes:
        apply_correction(document)
        document.quality_stage = "correct" if document.quality_stage in {"", "recognize"} else document.quality_stage
    if any(item.translated_text.strip() for item in document.segments):
        if document.quality_stage in {"", "recognize", "correct", "translate"}:
            document.quality_stage = "review"
    need_translation = expect_translation(document)
    consistency = document_term_consistency(document.segments, resources)
    cues: list[CueQuality] = []
    below: list[int] = []
    for index, segment in enumerate(document.segments):
        issues = inspect_segment(
            document.segments,
            index,
            expect_translation=need_translation,
            resources=resources,
        )
        recognition = round(recognition_score(segment.confidence, bool(segment.display_text().strip())), 1)
        translation = round(
            translation_score(
                segment.display_text(),
                segment.translated_text,
                expect_translation=need_translation,
            ),
            1,
        )
        cons = consistency.get(index, 100.0)
        if any(item.code == "consistency" for item in issues):
            cons = min(cons, 55.0)
        cons = round(cons, 1)
        qa = round(clamp_score(100.0 - sum(item.penalty for item in issues)), 1)
        composite = round(clamp_score(0.25 * recognition + 0.25 * translation + 0.20 * cons + 0.30 * qa), 1)
        qa_extra = segment.extra.get("qa") if isinstance(segment.extra, dict) else {}
        confirmed = bool(isinstance(qa_extra, dict) and qa_extra.get("confirmed"))
        row = CueQuality(
            cue_index=index,
            cue_id=segment.id,
            recognition=recognition,
            translation=translation,
            consistency=cons,
            qa=qa,
            composite=composite,
            band=band_for(composite),
            issues=issues,
            confirmed=confirmed,
            locked=segment.locked,
            cps=cps_of(segment),
        )
        segment.extra["qa"] = {**row.to_extra(), "confirmed": confirmed}
        cues.append(row)
        if composite < 90:
            below.append(index)
    if document.quality_stage in {"", "recognize", "correct", "translate", "review"}:
        document.quality_stage = "qa"
    score = sum(item.composite for item in cues) / len(cues) if cues else 100.0
    return QualityReport(
        cues=cues,
        stage=document.quality_stage or "qa",
        document_score=round(score, 1),
        issue_count=sum(len(item.issues) for item in cues),
        below_90=below,
    )


def score_cues(cues: list[SubtitleCue]) -> dict[str, float]:
    if not cues:
        return {"composite": 100.0, "overlap": 0.0, "cps_mean": 0.0, "too_short": 0.0, "too_long": 0.0}
    overlap = 0.0
    short = 0.0
    long = 0.0
    cps_total = 0.0
    for index, cue in enumerate(cues):
        span = max(0, cue.end_ms - cue.start_ms)
        chars = len((cue.text or "").replace(" ", ""))
        cps_total += (chars / (span / 1000.0)) if span else 0.0
        if span and span < 833:
            short += 1
        if span > 7000:
            long += 1
        for other in cues[index + 1 :]:
            if cue.start_ms < other.end_ms and other.start_ms < cue.end_ms:
                overlap += 1
                break
    count = float(len(cues))
    return {
        "overlap": overlap,
        "cps_mean": round(cps_total / count, 2),
        "too_short": short,
        "too_long": long,
        "composite": clamp_score(100.0 - overlap * 18 - short * 8 - long * 6),
    }


def next_issue_index(document: SubtitleDocument, current: int = -1) -> int | None:
    candidates: list[int] = []
    for index, segment in enumerate(document.segments):
        payload = segment.extra.get("qa") if isinstance(segment.extra, dict) else {}
        if not isinstance(payload, dict):
            continue
        issues = payload.get("issues") or []
        try:
            score = float(payload.get("composite", 100.0))
        except (TypeError, ValueError):
            score = 100.0
        if issues or score < 90:
            candidates.append(index)
    if not candidates:
        return None
    for index in candidates:
        if index > current:
            return index
    return candidates[0]


def _confirmed_or_locked(segment: SubtitleSegment) -> bool:
    if segment.locked:
        return True
    qa = segment.extra.get("qa") if isinstance(segment.extra, dict) else {}
    return bool(isinstance(qa, dict) and qa.get("confirmed"))
