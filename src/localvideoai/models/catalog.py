"""Replaceable model catalog. Engines do not hardcode display metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import ModelError
from localvideoai.core.paths import config_file


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    name: str
    type: str
    capability: str
    local_id: str
    languages: str
    size_bytes: int
    quantization: str
    ram_gb: float
    vram_gb: float
    kind: str
    source: str
    repo: str = ""

    def required_fields(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "languages": self.languages,
            "size_bytes": self.size_bytes,
            "quantization": self.quantization,
            "ram_gb": self.ram_gb,
            "vram_gb": self.vram_gb,
        }


def catalog_path() -> Path:
    return config_file("model_catalog.json")


def load_model_catalog() -> list[CatalogEntry]:
    path = catalog_path()
    if not path.is_file():
        raise ModelError(f"缺少模型目录文件：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelError(f"模型目录不是有效 JSON：{path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ModelError(f"模型目录格式错误：{path}")
    entries: list[CatalogEntry] = []
    seen: set[str] = set()
    for raw in payload["models"]:
        if not isinstance(raw, dict):
            raise ModelError("模型目录中存在无效条目")
        entry = _parse_entry(raw)
        if entry.id in seen:
            raise ModelError(f"模型目录重复 ID：{entry.id}")
        seen.add(entry.id)
        entries.append(entry)
    return entries


def catalog_by_id() -> dict[str, CatalogEntry]:
    return {entry.id: entry for entry in load_model_catalog()}


def _parse_entry(raw: dict[str, Any]) -> CatalogEntry:
    required = ("id", "name", "type", "capability", "local_id", "languages", "size_bytes", "quantization", "ram_gb", "vram_gb")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ModelError(f"模型目录缺少字段：{', '.join(missing)}")
    return CatalogEntry(
        id=str(raw["id"]),
        name=str(raw["name"]),
        type=str(raw["type"]),
        capability=str(raw["capability"]),
        local_id=str(raw["local_id"]),
        languages=str(raw["languages"]),
        size_bytes=int(raw["size_bytes"]),
        quantization=str(raw["quantization"]),
        ram_gb=float(raw["ram_gb"]),
        vram_gb=float(raw["vram_gb"]),
        kind=str(raw.get("kind") or ""),
        source=str(raw.get("source") or ""),
        repo=str(raw.get("repo") or ""),
    )
