"""Download one faster-whisper CTranslate2 model into the project models/speech/ tree."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from localvideoai.core.paths import install_root
from localvideoai.speech.store import KNOWN_MODELS, download_model, is_model_ready


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_id", choices=sorted(KNOWN_MODELS))
    args = parser.parse_args()
    os.environ.setdefault("LOCALVIDEOAI_MODELS_DIR", str(install_root() / "models"))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    os.environ["HF_HUB_OFFLINE"] = "0"
    if is_model_ready(args.model_id):
        print(f"already present: {args.model_id}")
        return 0
    print(f"downloading {args.model_id} ({KNOWN_MODELS[args.model_id]}) ...", flush=True)
    path = download_model(args.model_id)
    bin_path = Path(path) / "model.bin"
    print(f"saved {path} bin={bin_path.stat().st_size if bin_path.is_file() else 0}", flush=True)
    if not is_model_ready(args.model_id):
        raise SystemExit(f"model incomplete: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
