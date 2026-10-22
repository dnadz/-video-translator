"""Local license files. Core features stay usable without a license."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from localvideoai import APP_ID
from localvideoai.core.paths import user_data_dir

SCHEMA = 1
EDITION_LOCAL = "local"
EDITION_STUDIO = "studio"
_HMAC_KEY = b"LocalVideoAI-license-v1:" + APP_ID.encode("ascii")


@dataclass(frozen=True)
class LicenseInfo:
    edition: str
    issued_to: str
    expires: str
    valid: bool
    reason: str
    path: Path | None = None

    @property
    def label(self) -> str:
        if self.edition == EDITION_STUDIO and self.valid:
            return f"Studio（{self.issued_to or '已授权'}）"
        if self.valid:
            return "本机个人版（无需授权文件）"
        return f"授权无效：{self.reason}"


def default_license_path() -> Path:
    return user_data_dir() / "license.json"


def unsigned_local() -> LicenseInfo:
    return LicenseInfo(
        edition=EDITION_LOCAL,
        issued_to="",
        expires="",
        valid=True,
        reason="未导入授权文件，按本机个人版运行，功能完整",
    )


def sign_payload(payload: dict[str, Any]) -> str:
    return hmac.new(_HMAC_KEY, _canonical(payload), hashlib.sha256).hexdigest()


def issue_license(*, issued_to: str, edition: str = EDITION_STUDIO, expires: str = "") -> dict[str, Any]:
    payload = {
        "schema": SCHEMA,
        "edition": edition,
        "issued_to": issued_to.strip(),
        "expires": expires.strip(),
    }
    payload["signature"] = sign_payload(payload)
    return payload


def load_license(path: Path | None = None) -> LicenseInfo:
    target = path or default_license_path()
    if not target.is_file():
        return unsigned_local()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return LicenseInfo(EDITION_LOCAL, "", "", False, f"授权文件无法读取：{exc}", target)
    if not isinstance(data, dict):
        return LicenseInfo(EDITION_LOCAL, "", "", False, "授权文件格式错误", target)
    edition = str(data.get("edition") or EDITION_LOCAL).strip() or EDITION_LOCAL
    issued_to = str(data.get("issued_to") or "").strip()
    expires = str(data.get("expires") or "").strip()
    signature = str(data.get("signature") or "").strip()
    expected = sign_payload(
        {"schema": int(data.get("schema") or SCHEMA), "edition": edition, "issued_to": issued_to, "expires": expires}
    )
    if not signature or not hmac.compare_digest(signature, expected):
        return LicenseInfo(edition, issued_to, expires, False, "授权签名不匹配", target)
    if expires:
        try:
            if date.fromisoformat(expires) < date.today():
                return LicenseInfo(edition, issued_to, expires, False, f"授权已于 {expires} 过期", target)
        except ValueError:
            return LicenseInfo(edition, issued_to, expires, False, "到期日格式无效", target)
    return LicenseInfo(edition, issued_to, expires, True, "授权有效", target)


def save_license(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or default_license_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _canonical(payload: dict[str, Any]) -> bytes:
    body = {
        "schema": int(payload.get("schema") or SCHEMA),
        "edition": str(payload.get("edition") or ""),
        "issued_to": str(payload.get("issued_to") or ""),
        "expires": str(payload.get("expires") or ""),
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
