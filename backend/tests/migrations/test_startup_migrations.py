import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.config import Settings
from app.main import create_app
from app.schema_guard import LegacyDatabaseError


def development_settings(tmp_path):
    return Settings(
        app_env="development",
        database_url=f"sqlite:///{tmp_path / 'meetflow.db'}",
        data_dir=tmp_path / "data",
        plugins_dir=tmp_path / "plugins",
        frontend_dist=tmp_path / "frontend",
        admin_username="admin",
        admin_password="correct-horse-battery",
        app_secret_key="test-secret-key-with-at-least-32-chars",
    )


def test_development_startup_migrates_and_bootstraps_fresh_database(tmp_path):
    app = create_app(development_settings(tmp_path))

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    database = app.state.database
    tables = set(inspect(database.engine).get_table_names())
    assert {"alembic_version", "users", "meetings"} <= tables
    with database.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0001"
        )
        assert connection.scalar(text("SELECT username FROM users")) == "admin"


def test_development_startup_rejects_legacy_database_before_changes(tmp_path):
    settings = development_settings(tmp_path)
    path = tmp_path / "meetflow.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE meetings (id TEXT PRIMARY KEY, project TEXT)")
        connection.execute("INSERT INTO meetings VALUES ('meeting-1', 'MeetFlow')")
    original_bytes = path.read_bytes()
    app = create_app(settings)

    with pytest.raises(LegacyDatabaseError, match="v0.1"):
        with TestClient(app):
            pass

    assert path.read_bytes() == original_bytes
    assert not path.with_name("meetflow.db-wal").exists()
    assert not path.with_name("meetflow.db-shm").exists()
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall() == [("meetings",)]
        assert connection.execute("SELECT * FROM meetings").fetchall() == [
            ("meeting-1", "MeetFlow")
        ]
