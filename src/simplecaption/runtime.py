"""Find the existing local model tree without hardcoding a machine path."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SPEECH_READY = ("model.bin", "config.json")


def prepare_runtime() -> Path | None:
    """Point model lookup at a discovered tree only when the default lookup is empty."""
    override = os.environ.get("LOCALVIDEOAI_MODELS_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    found = find_models_tree()
    if found is None:
        return None
    if _default_lookup_works():
        return found
    os.environ["LOCALVIDEOAI_MODELS_DIR"] = str(found)
    return found


def find_models_tree() -> Path | None:
    seen: set[Path] = set()
    for start in _search_starts():
        for candidate in [start, *start.parents]:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            models = resolved / "models"
            if _has_speech_model(models / "speech"):
                return models
    return None


def _search_starts() -> list[Path]:
    starts = [Path.cwd(), Path(__file__).resolve()]
    if getattr(sys, "frozen", False):
        starts.insert(0, Path(sys.executable).resolve().parent)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        starts.append(Path(meipass))
    return starts


def _has_speech_model(speech_dir: Path) -> bool:
    if not speech_dir.is_dir():
        return False
    try:
        children = list(speech_dir.iterdir())
    except OSError:
        return False
    for child in children:
        if child.is_dir() and all((child / name).is_file() for name in _SPEECH_READY):
            return True
    return False


def _default_lookup_works() -> bool:
    from localvideoai.speech.store import list_local_models
    from localvideoai.translation.store import list_local_translation_models

    return bool(list_local_models()) and bool(list_local_translation_models())
