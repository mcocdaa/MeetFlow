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
    database = Database(f"sqlite:///{path}")

    with pytest.raises(LegacyDatabaseError, match="v0.1"):
        reject_legacy_schema(database.engine)

    assert path.exists()
