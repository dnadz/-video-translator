"""Transcribe with hub offline flags. Models must already be on disk."""

from __future__ import annotations

import os
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from localvideoai.core.paths import install_root
from localvideoai.engines.faster_whisper_engine import FasterWhisperSpeechEngine


def main() -> int:
    source = install_root() / "test_assets" / "audio" / "phase6" / "zh_normal.wav"
    if not source.is_file():
        raise SystemExit(f"missing {source}")
    dest = install_root() / "test_assets" / "audio" / "phase6" / "offline_transcript.json"
    transcript = FasterWhisperSpeechEngine().transcribe_media(
        source,
        language="zh",
        model_id="small",
        raw_path=dest,
    )
    print(f"offline_ok device={transcript.device} language={transcript.language} segments={len(transcript.segments)}")
    print(transcript.segments[0].text)
    print(f"raw={transcript.raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
