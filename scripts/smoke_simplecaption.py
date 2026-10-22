"""Run one local file through the same engines as the simple window."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from simplecaption.runtime import prepare_runtime
from simplecaption.smoke import run_smoke

if __name__ == "__main__":
    prepare_runtime()
    media = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "test_assets" / "simplecaption" / "hello.wav")
    raise SystemExit(run_smoke(media))
