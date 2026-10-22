"""Confirm medium is selectable and transcribe a short local clip."""

from __future__ import annotations

from pathlib import Path

from localvideoai.hardware.hardware_manager import HardwareManager
from localvideoai.speech.selector import select_speech_model
from localvideoai.speech.store import is_model_ready, list_local_models


def main() -> int:
    lines = [f"local_models={list_local_models()}", f"medium_ready={is_model_ready('medium')}"]
    report = HardwareManager().detect()
    available = set(list_local_models())
    choice = select_speech_model(report, prefer_gpu=True, available=available)
    lines.append(f"turbo_ready={is_model_ready('large-v3-turbo')}")
    lines.append(f"choice={choice.model_id} device={choice.device} compute={choice.compute_type}")
    lines.append(f"reason={choice.reason}")
    clip = Path("test_assets") / "audio" / "phase6" / "zh_normal.mp4"
    if clip.is_file():
        from localvideoai.engines import create_speech_engine

        engine = create_speech_engine(report)
        result = engine.transcribe_media(clip, language="zh")
        text = " ".join(seg.text for seg in result.segments)
        lines.append(f"clip={clip}")
        lines.append(f"asr_model={result.model_id} device={result.device}")
        lines.append(f"asr_text={text}")
    else:
        lines.append(f"clip missing: {clip}")
    out = Path("logs") / "p0_asr_probe.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
