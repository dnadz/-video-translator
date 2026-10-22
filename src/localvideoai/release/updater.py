"""Opt-in update check. Never runs unless the user asks. Default is offline."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from localvideoai import __version__
from localvideoai.core.exceptions import ConfigurationError
from localvideoai.core.paths import default_config_path


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    latest: str
    available: bool
    notes: str
    setup_url: str
    source: str
    reason: str


def parse_version(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in (text or "0").split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or (0,))


def check_for_update(source: str, *, current: str | None = None, allow_network: bool = False) -> UpdateInfo:
    now = current or __version__
    raw = (source or "").strip()
    if not raw:
        fallback = default_config_path().parent / "update-manifest.json"
        if fallback.is_file():
            raw = str(fallback)
        else:
            return UpdateInfo(now, now, False, "", "", "", "未配置更新源")
    payload = _read_manifest(raw, allow_network=allow_network)
    latest = str(payload.get("version") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    setup_url = str(payload.get("setup_url") or payload.get("url") or "").strip()
    if not latest:
        raise ConfigurationError("更新清单缺少 version")
    available = parse_version(latest) > parse_version(now)
    reason = f"发现新版本 {latest}" if available else f"已是最新（{now}）"
    return UpdateInfo(now, latest, available, notes, setup_url, raw, reason)


def _read_manifest(source: str, *, allow_network: bool) -> dict:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        if not allow_network:
            raise ConfigurationError("检查在线更新需要先允许联网，且必须由你手动点「检查更新」。")
        request = urllib.request.Request(source, headers={"User-Agent": "LocalVideoAI-Updater/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return _parse_json(response.read().decode("utf-8"), source)
    path = Path(source[7:] if source.lower().startswith("file://") else source).expanduser()
    if not path.is_file():
        raise ConfigurationError(f"本地更新清单不存在：{path}")
    return _parse_json(path.read_text(encoding="utf-8"), path)


def _parse_json(text: str, origin: object) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"更新清单不是 JSON：{origin}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"更新清单必须是对象：{origin}")
    return data
