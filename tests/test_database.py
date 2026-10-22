from localvideoai.db.database import SCHEMA_VERSION, Database
from localvideoai.core.paths import database_path


def test_database_connect_and_ping(isolated_env):
    db = Database()
    conn = db.connect()
    try:
        assert db.ping() is True
        assert db.schema_version() == SCHEMA_VERSION
        assert database_path().is_file()
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
        assert row is not None
    finally:
        db.close()
