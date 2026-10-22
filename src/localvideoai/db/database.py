from __future__ import annotations

import sqlite3
from pathlib import Path

from localvideoai.core.exceptions import DatabaseError
from localvideoai.core.paths import database_path, ensure_directory

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
"""


class Database:
    """SQLite connection used by TaskManager and later project metadata."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or database_path()
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        try:
            ensure_directory(self.path.parent)
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Cannot initialize SQLite database: {self.path}") from exc
        except OSError as exc:
            raise DatabaseError(f"Cannot create database directory for: {self.path}") from exc
        self._conn = conn
        return conn

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("Database is not connected.")
        return self._conn

    def ping(self) -> bool:
        try:
            row = self.connection.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("SQLite ping failed.") from exc
        return row is not None and int(row[0]) == 1

    def schema_version(self) -> int:
        try:
            row = self.connection.execute(
                "SELECT value FROM schema_meta WHERE key = ?",
                ("schema_version",),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("Cannot read schema version.") from exc
        if row is None:
            raise DatabaseError("schema_version is missing.")
        return int(row[0])

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
