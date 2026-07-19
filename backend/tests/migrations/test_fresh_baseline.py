import sqlite3

import pytest
from sqlalchemy import inspect

from app.database import Database
from app.schema_guard import LegacyDatabaseError, reject_legacy_schema


def test_fresh_database_upgrades_to_head(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'fresh.db'}")

    database.migrate()

    tables = set(inspect(database.engine).get_table_names())
    assert {"alembic_version", "users", "meetings"} <= tables


def test_v01_database_is_rejected_without_deletion(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE meetings (id TEXT PRIMARY KEY, project TEXT)")
        connection.execute("INSERT INTO meetings VALUES ('meeting-1', 'MeetFlow')")
        original_journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    original_bytes = path.read_bytes()
    database = Database(f"sqlite:///{path}")

    with pytest.raises(LegacyDatabaseError, match="v0.1"):
        reject_legacy_schema(database.engine)

    assert path.exists()
    assert path.read_bytes() == original_bytes
    assert not path.with_name("legacy.db-wal").exists()
    assert not path.with_name("legacy.db-shm").exists()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == (
            original_journal_mode
        )
        assert connection.execute("PRAGMA table_info(meetings)").fetchall() == [
            (0, "id", "TEXT", 0, None, 1),
            (1, "project", "TEXT", 0, None, 0),
        ]
        assert connection.execute("SELECT * FROM meetings").fetchall() == [
            ("meeting-1", "MeetFlow")
        ]
