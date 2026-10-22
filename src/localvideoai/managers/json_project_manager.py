from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import PathError
from localvideoai.core.paths import ensure_directory
from localvideoai.managers.project_manager import ProjectManager
from localvideoai.project.schema import (
    PROJECT_EXTENSION,
    PROJECT_KIND,
    SCHEMA_VERSION,
    empty_project,
    merge_project,
    normalize_project_path,
    sanitize_filename,
    utc_now,
)

PROJECT_FILENAME = f"project{PROJECT_EXTENSION}"


class JsonProjectManager(ProjectManager):
    """UTF-8 .vtproj (JSON) on local disk. Still loads legacy project.json."""

    def create(self, name: str, directory: Path) -> Path:
        if not name.strip():
            raise PathError("项目名称不能为空。")
        ensure_directory(directory)
        path = directory / f"{sanitize_filename(name.strip())}{PROJECT_EXTENSION}"
        return self.save(path, empty_project(name.strip()))

    def load(self, project_file: Path) -> dict[str, Any]:
        try:
            raw = project_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise PathError(f"无法读取项目文件：{project_file}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PathError(f"项目文件不是有效 JSON：{project_file}") from exc
        if not isinstance(data, dict):
            raise PathError(f"项目文件根对象无效：{project_file}")
        merged = merge_project(data)
        if not merged.get("name"):
            merged["name"] = project_file.stem
        return merged

    def save(self, project_file: Path, data: dict[str, Any]) -> Path:
        destination = project_file if project_file.name.lower() == "project.json" else normalize_project_path(project_file)
        payload = merge_project(deepcopy(data))
        payload["schema_version"] = SCHEMA_VERSION
        payload["kind"] = PROJECT_KIND
        payload["updated_at"] = utc_now()
        payload["dirty"] = False
        ensure_directory(destination.parent)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(destination)
        except OSError as exc:
            raise PathError(f"无法保存项目文件：{destination}") from exc
        return destination
