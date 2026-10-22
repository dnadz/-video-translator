"""Translate offline. Models must already be on disk."""

from __future__ import annotations

import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from localvideoai.core.types import TranslationRequest
from localvideoai.engines.ctranslate2_translation_engine import CTranslate2TranslationEngine


def main() -> int:
    engine = CTranslate2TranslationEngine()
    cases = [
        ("今天天气很好。", "zh", "en"),
        ("The weather is nice today.", "en", "zh"),
        ("本日は晴天なり。", "ja", "zh"),
    ]
    for text, source, target in cases:
        result = engine.translate(TranslationRequest(text=text, source_lang=source, target_lang=target))
        print(f"{source}->{target} model={result.model_id} device={result.device}")
        print(f"  src: {text}")
        print(f"  tgt: {result.text}")
        if not result.text or result.text.strip() == text.strip():
            raise SystemExit(f"translation produced no new text for {source}->{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
