"""Download faster-whisper large-v3-turbo into the workspace speech folder.

Weights stay out of the EXE. End users install the same model from the in-app
model center into the managed models directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from localvideoai.core.paths import install_root
from localvideoai.speech.store import KNOWN_MODELS, _speech_ready, download_model, is_model_ready


def _destination(model_id: str) -> Path:
    return install_root() / "models" / "speech" / model_id


def _install(model_id: str) -> Path:
    dest = _destination(model_id)
    if _speech_ready(dest) or is_model_ready(model_id):
        print(f"already present: {model_id}")
        return dest
    if dest.exists() and not _speech_ready(dest):
        shutil.rmtree(dest)
    print(f"downloading {model_id} ({KNOWN_MODELS[model_id]}) -> {dest}")
    path = download_model(model_id, destination=dest)
    print(f"saved {path}")
    return path


def main() -> int:
    try:
        _install("large-v3-turbo")
    except Exception as exc:
        print(f"large-v3-turbo failed: {exc}")
        print("falling back to medium")
        _install("medium")
    ready = [name for name in ("large-v3-turbo", "medium") if _speech_ready(_destination(name)) or is_model_ready(name)]
    if not ready:
        raise SystemExit("P0 speech models missing after download")
    print(f"ready: {ready}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
