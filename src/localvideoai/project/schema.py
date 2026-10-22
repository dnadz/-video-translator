"""LocalVideoAI .vtproj schema. JSON on disk; never uploaded."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
PROJECT_KIND = "localvideoai-vtproj"
PROJECT_EXTENSION = ".vtproj"
LEGACY_FILENAME = "project.json"

REQUIRED_SECTIONS = (
    "video_info",
    "videos",
    "subtitles",
    "document",
    "ocr",
    "speech",
    "translation",
    "speakers",
    "terms",
    "timeline",
    "styles",
    "export",
    "models",
    "tasks",
    "locks",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name.strip()) or "project"
    return cleaned[:80]


def normalize_project_path(path: Path) -> Path:
    if path.suffix.lower() == PROJECT_EXTENSION:
        return path
    if path.name.lower() == LEGACY_FILENAME:
        return path
    return path.with_suffix(PROJECT_EXTENSION)


def empty_project(name: str) -> dict[str, Any]:
    stamp = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PROJECT_KIND,
        "project_id": uuid.uuid4().hex,
        "name": name,
        "created_at": stamp,
        "updated_at": stamp,
        "dirty": False,
        "videos": [],
        "subtitles": [],
        "batch_items": [],
        "current_video": "",
        "video_info": {},
        "document": None,
        "ocr": {"region": None, "region_source": "auto"},
        "speech": {"language": "auto", "model_id": "", "device": ""},
        "translation": {
            "source_lang": "auto",
            "target_lang": "zh-CN",
            "quality": "standard",
            "extra_targets": [],
        },
        "speakers": {"map": {}, "styles": {}},
        "terms": {"glossary": [], "translation_memory": [], "character_dictionary": []},
        "timeline": {
            "position_ms": 0,
            "duration_ms": 0,
            "rate": 1.0,
            "volume": 0.8,
            "muted": False,
        },
        "styles": {"speaker_styles": {}, "default_style": ""},
        "export": {"format": "srt", "burn_in": False, "output_dir": "", "container": "mp4", "video_codec": "copy"},
        "models": {
            "speech": "",
            "ocr": "",
            "translation": "",
            "speaker": "",
            "device": "auto",
            "prefer_gpu": True,
        },
        "tasks": [],
        "locks": {"locked_ids": [], "confirmed_ids": []},
        "session": {"last_page": "workspace"},
    }


def merge_project(data: dict[str, Any]) -> dict[str, Any]:
    base = empty_project(str(data.get("name") or "未命名项目"))
    if data.get("project_id"):
        base["project_id"] = str(data["project_id"])
    for key, value in data.items():
        if key in {"created_at"} and value:
            base[key] = value
            continue
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merged = dict(base[key])
            merged.update(value)
            base[key] = merged
        else:
            base[key] = value
    base["schema_version"] = SCHEMA_VERSION
    base["kind"] = PROJECT_KIND
    return base
