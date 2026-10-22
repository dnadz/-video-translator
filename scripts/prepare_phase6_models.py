"""Download faster-whisper CTranslate2 models into models/speech/. Run online once."""

from __future__ import annotations

from localvideoai.speech.store import KNOWN_MODELS, download_model, is_model_ready, speech_models_dir


def main() -> int:
    wanted = ("tiny", "small")
    print(f"model root: {speech_models_dir()}")
    for model_id in wanted:
        if is_model_ready(model_id):
            print(f"already present: {model_id} -> {KNOWN_MODELS[model_id]}")
            continue
        print(f"downloading {model_id} ({KNOWN_MODELS[model_id]}) ...")
        path = download_model(model_id)
        print(f"saved {path}")
    missing = [name for name in wanted if not is_model_ready(name)]
    if missing:
        raise SystemExit(f"models missing after download: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
