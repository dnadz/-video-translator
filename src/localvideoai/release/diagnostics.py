"""Pack local logs for the user. Never uploads."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from localvideoai.core.paths import logs_dir, user_data_dir


def export_crash_bundle(destination: Path | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = destination or (user_data_dir() / "diagnostics" / f"LocalVideoAI-diag-{stamp}.zip")
    dest = dest.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    root = logs_dir()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and path.stat().st_size < 20_000_000:
                    archive.write(path, Path("logs") / path.relative_to(root))
        archive.writestr(
            "README.txt",
            "本机诊断包，未上传。可自行发送给维护者。其中不应包含视频或字幕原文。\n",
        )
    return dest
