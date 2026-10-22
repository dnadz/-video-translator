"""Quality report types. Scores are deterministic, never random."""

from __future__ import annotations

from dataclasses import dataclass, field

BAND_GREEN = "green"
BAND_YELLOW = "yellow"
BAND_RED = "red"

HIGH_QUALITY = 90
REVIEW_QUALITY = 70

STAGES = (
    "recognize",
    "correct",
    "translate",
    "review",
    "qa",
    "confirm",
    "lock",
)

STAGE_LABELS = {
    "recognize": "识别",
    "correct": "纠错",
    "translate": "翻译",
    "review": "翻译审核",
    "qa": "QA",
    "confirm": "人工确认",
    "lock": "锁定",
}

BAND_LABELS = {
    BAND_GREEN: "高质量",
    BAND_YELLOW: "建议检查",
    BAND_RED: "需要人工检查",
}


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str
    penalty: int
    cue_index: int
    cue_id: int


@dataclass
class CueQuality:
    cue_index: int
    cue_id: int
    recognition: float
    translation: float
    consistency: float
    qa: float
    composite: float
    band: str
    issues: list[QualityIssue] = field(default_factory=list)
    confirmed: bool = False
    locked: bool = False
    cps: float = 0.0

    def to_extra(self) -> dict[str, object]:
        return {
            "recognition": round(self.recognition, 1),
            "translation": round(self.translation, 1),
            "consistency": round(self.consistency, 1),
            "qa": round(self.qa, 1),
            "composite": round(self.composite, 1),
            "band": self.band,
            "cps": round(self.cps, 2),
            "confirmed": self.confirmed,
            "issues": [
                {"code": item.code, "message": item.message, "penalty": item.penalty} for item in self.issues
            ],
        }


@dataclass
class QualityReport:
    cues: list[CueQuality]
    stage: str
    document_score: float
    issue_count: int
    below_90: list[int] = field(default_factory=list)

    def cue(self, index: int) -> CueQuality | None:
        for item in self.cues:
            if item.cue_index == index:
                return item
        return None


def band_for(score: float) -> str:
    if score >= HIGH_QUALITY:
        return BAND_GREEN
    if score >= REVIEW_QUALITY:
        return BAND_YELLOW
    return BAND_RED


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def format_stage_pipeline(stage: str) -> str:
    parts: list[str] = []
    for key in STAGES:
        label = STAGE_LABELS[key]
        parts.append(f"【{label}】" if key == stage else label)
    return " → ".join(parts)
