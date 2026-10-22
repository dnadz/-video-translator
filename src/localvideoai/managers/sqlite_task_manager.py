"""SQLite TaskManager. Tasks survive process exit; completed ones stay skippable."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from localvideoai.core.exceptions import DatabaseError, TaskError
from localvideoai.core.types import TaskSpec
from localvideoai.db.database import Database
from localvideoai.managers.task_manager import TaskManager


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SqliteTaskManager(TaskManager):
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()
        self._lock = threading.RLock()
        if database is None or getattr(database, "_conn", None) is None:
            self._db.connect()

    @property
    def database(self) -> Database:
        return self._db

    def enqueue(self, spec: TaskSpec) -> str:
        task_id = spec.task_id or uuid.uuid4().hex
        stamp = _now()
        payload = dict(spec.payload)
        payload.setdefault("task_id", task_id)
        try:
            with self._lock:
                self._db.connection.execute(
                    "INSERT INTO tasks(id, type, status, created_at, updated_at, payload_json) VALUES(?,?,?,?,?,?)",
                    (task_id, spec.task_type or "batch_video", "等待", stamp, stamp, json.dumps(payload, ensure_ascii=False)),
                )
                self._db.connection.commit()
        except Exception as exc:
            raise TaskError(f"无法写入任务：{task_id}") from exc
        return task_id

    def get(self, task_id: str) -> dict[str, Any] | None:
        try:
            with self._lock:
                row = self._db.connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        except Exception as exc:
            raise TaskError(f"无法读取任务：{task_id}") from exc
        return _row_to_task(row) if row is not None else None

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        try:
            with self._lock:
                if status:
                    rows = self._db.connection.execute(
                        "SELECT * FROM tasks WHERE status = ? ORDER BY created_at, id",
                        (status,),
                    ).fetchall()
                else:
                    rows = self._db.connection.execute("SELECT * FROM tasks ORDER BY created_at, id").fetchall()
        except Exception as exc:
            raise TaskError("无法列出任务") from exc
        return [_row_to_task(row) for row in rows]

    def update(self, task_id: str, **fields: Any) -> dict[str, Any]:
        current = self.get(task_id)
        if current is None:
            raise TaskError(f"任务不存在：{task_id}")
        status = str(fields.pop("status", current["status"]))
        payload = dict(current.get("payload") or {})
        extra = fields.pop("payload", None)
        if isinstance(extra, dict):
            payload.update(extra)
        payload.update(fields)
        payload["status"] = status
        payload["task_id"] = task_id
        try:
            with self._lock:
                self._db.connection.execute(
                    "UPDATE tasks SET status = ?, updated_at = ?, payload_json = ? WHERE id = ?",
                    (status, _now(), json.dumps(payload, ensure_ascii=False), task_id),
                )
                self._db.connection.commit()
        except Exception as exc:
            raise TaskError(f"无法更新任务：{task_id}") from exc
        updated = self.get(task_id)
        if updated is None:
            raise TaskError(f"更新后读不到任务：{task_id}")
        return updated

    def delete(self, task_id: str) -> None:
        try:
            with self._lock:
                self._db.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                self._db.connection.commit()
        except Exception as exc:
            raise TaskError(f"无法删除任务：{task_id}") from exc

    def close(self) -> None:
        try:
            self._db.close()
        except DatabaseError:
            pass


def create_task_manager(database: Database | None = None) -> TaskManager:
    return SqliteTaskManager(database)


def _row_to_task(row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"] or "{}")
    if not isinstance(payload, dict):
        payload = {}
    return {
        "id": row["id"],
        "type": row["type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "payload": payload,
    }
