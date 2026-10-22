"""Write a complete local project export folder. Does not upload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import ExportError
from localvideoai.core.paths import ensure_directory
from localvideoai.managers.json_project_manager import JsonProjectManager
from localvideoai.project.schema import sanitize_filename


def write_project_bundle(directory: Path, payload: dict[str, Any] | None, name: str) -> Path:
    root = ensure_directory(directory)
    if payload is None:
        raise ExportError("完整项目导出需要项目数据")
    project_path = root / f"{sanitize_filename(name)}.vtproj"
    JsonProjectManager().save(project_path, payload)
    manifest = {
        "kind": "localvideoai-export",
        "name": name,
        "project": project_path.name,
        "notes": "视频、字幕和项目文件都在本机目录，不会上传。",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return project_path
