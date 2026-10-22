"""Autosave journal. A leftover dirty session means the last run did not close cleanly."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import PathError
from localvideoai.core.paths import ensure_directory, recovery_dir
from localvideoai.project.schema import utc_now

SESSION_NAME = "session.json"
AUTOSAVE_NAME = "autosave.vtproj"


class RecoveryJournal:
    def __init__(self, root: Path | None = None) -> None:
        self.root = ensure_directory(root or recovery_dir())
        self.session_path = self.root / SESSION_NAME
        self.autosave_path = self.root / AUTOSAVE_NAME

    def read_session(self) -> dict[str, Any] | None:
        if not self.session_path.is_file():
            return None
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def write_session(self, **fields: Any) -> dict[str, Any]:
        current = self.read_session() or {}
        current.update(fields)
        current["updated_at"] = utc_now()
        current["pid"] = os.getpid()
        current["autosave_path"] = str(self.autosave_path)
        self._write(self.session_path, current)
        return current

    def mark_open(self, project_path: Path | None) -> None:
        self.write_session(project_path=str(project_path) if project_path else "", dirty=False, closed_clean=False)

    def mark_dirty(self, project_path: Path | None = None) -> None:
        payload: dict[str, Any] = {"dirty": True, "closed_clean": False}
        if project_path is not None:
            payload["project_path"] = str(project_path)
        self.write_session(**payload)

    def mark_clean(self, project_path: Path | None = None) -> None:
        payload: dict[str, Any] = {"dirty": False}
        if project_path is not None:
            payload["project_path"] = str(project_path)
        self.write_session(**payload)

    def mark_closed(self) -> None:
        self.write_session(dirty=False, closed_clean=True)

    def clear(self) -> None:
        for path in (self.session_path, self.autosave_path):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise PathError(f"无法清除恢复文件：{path}") from exc

    def write_autosave(self, data: dict[str, Any]) -> Path:
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        tmp = self.autosave_path.with_suffix(self.autosave_path.suffix + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(self.autosave_path)
        except OSError as exc:
            raise PathError(f"无法写入自动保存：{self.autosave_path}") from exc
        self.mark_dirty(Path(str(data.get("path") or "")) if data.get("path") else None)
        return self.autosave_path

    def read_autosave(self) -> dict[str, Any] | None:
        if not self.autosave_path.is_file():
            return None
        try:
            data = json.loads(self.autosave_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def unfinished(self) -> dict[str, Any] | None:
        session = self.read_session()
        if session is None:
            return None
        if session.get("closed_clean") and not session.get("dirty"):
            return None
        if not session.get("dirty") and not self.autosave_path.is_file():
            return None
        return {
            "session": session,
            "autosave": self.read_autosave(),
            "autosave_path": str(self.autosave_path) if self.autosave_path.is_file() else "",
            "project_path": str(session.get("project_path") or ""),
        }

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        ensure_directory(path.parent)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            raise PathError(f"无法写入恢复会话：{path}") from exc


def unfinished_session(root: Path | None = None) -> dict[str, Any] | None:
    return RecoveryJournal(root).unfinished()
