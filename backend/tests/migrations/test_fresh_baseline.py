import os
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.database import Database, migration_config_path
from app import schema_guard
from app.schema_guard import LegacyDatabaseError, reject_legacy_schema

APPLICATION_TABLES = {
    "action_items",
    "activity_events",
    "agenda_items",
    "attachments",
    "comment_mentions",
    "comments",
    "decision_reviewers",
    "decisions",
    "meeting_amendments",
    "meeting_participants",
    "meeting_series",
    "meeting_snapshots",
    "meetings",
    "notifications",
    "open_questions",
    "outcome_migration_records",
    "plugin_configs",
    "plugin_jobs",
    "plugin_states",
    "project_members",
    "project_updates",
    "projects",
    "series_participants",
    "standing_agenda_items",
    "user_work_briefs",
    "users",
}

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_fresh_database_upgrades_to_head(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'fresh.db'}")

    database.migrate()

    tables = set(inspect(database.engine).get_table_names())
    assert APPLICATION_TABLES | {"alembic_version"} <= tables
    inspector = inspect(database.engine)
    user_columns = {column["name"]: column for column in inspector.get_columns("users")}
    assert "avatar_color" in user_columns
    assert user_columns["avatar_color"]["nullable"] is False
    project_update_columns = {
        column["name"] for column in inspector.get_columns("project_updates")
    }
    assert "created_by" in project_update_columns
    assert "created_by_user_id" not in project_update_columns
    assert "author_id" not in project_update_columns
    assert {
        "id",
        "target_type",
        "target_id",
        "original_name",
        "stored_name",
        "mime_type",
        "size",
        "attachment_type",
        "created_by",
        "created_at",
    } <= {column["name"] for column in inspector.get_columns("attachments")}
    assert any(
        index["column_names"] == ["target_type", "target_id"]
        for index in inspector.get_indexes("attachments")
    )
    activity_columns = {
        column["name"]: column for column in inspector.get_columns("activity_events")
    }
    assert activity_columns["id"]["primary_key"] == 1
    activity_indexes = {
        tuple(index["column_names"])
        for index in inspector.get_indexes("activity_events")
    }
    assert {
        ("project_id",),
        ("meeting_id",),
        ("event_type",),
        ("subject_id",),
        ("created_at",),
    } <= activity_indexes
    activity_foreign_keys = {
        foreign_key["constrained_columns"][0]: foreign_key
        for foreign_key in inspector.get_foreign_keys("activity_events")
    }
    assert {
        key: value["options"].get("ondelete")
        for key, value in activity_foreign_keys.items()
    } == {
        "actor_user_id": "SET NULL",
        "meeting_id": "SET NULL",
        "project_id": "SET NULL",
    }
    comment_indexes = {
        tuple(index["column_names"]) for index in inspector.get_indexes("comments")
    }
    assert {
        ("project_id",),
        ("meeting_id",),
        ("target_type", "target_id"),
    } <= comment_indexes
    comment_foreign_keys = {
        foreign_key["constrained_columns"][0]: foreign_key
        for foreign_key in inspector.get_foreign_keys("comments")
    }
    assert {
        ("project_id", "CASCADE"),
        ("meeting_id", "SET NULL"),
    } <= {
        (key, value["options"].get("ondelete"))
        for key, value in comment_foreign_keys.items()
    }
    comment_columns = {
        column["name"]: column for column in inspector.get_columns("comments")
    }
    assert comment_columns["resolved_at"]["nullable"] is True
    assert comment_columns["resolved_by"]["nullable"] is True
    assert "resolved_by" in comment_foreign_keys
    plugin_job_indexes = {
        tuple(index["column_names"])
        for index in inspector.get_indexes("plugin_jobs")
        if index["unique"]
    }
    assert ("dedupe_key", "status") in plugin_job_indexes
    notification_indexes = {
        tuple(index["column_names"]) for index in inspector.get_indexes("notifications")
    }
    assert {
        ("user_id", "id"),
        ("user_id", "read_at", "id"),
    } <= notification_indexes
    notification_foreign_keys = {
        foreign_key["constrained_columns"][0]: foreign_key
        for foreign_key in inspector.get_foreign_keys("notifications")
    }
    assert {
        ("user_id", "CASCADE"),
        ("actor_user_id", "SET NULL"),
        ("project_id", "SET NULL"),
        ("meeting_id", "SET NULL"),
        ("source_comment_id", "SET NULL"),
    } <= {
        (key, value["options"].get("ondelete"))
        for key, value in notification_foreign_keys.items()
    }
    with database.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            ScriptDirectory.from_config(
                Config(migration_config_path())
            ).get_current_head()
        )


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


def test_v01_database_in_wal_is_rejected_without_modification(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE meetings (id TEXT PRIMARY KEY, project TEXT)")
        connection.execute("INSERT INTO meetings VALUES ('meeting-1', 'MeetFlow')")
        connection.commit()

        original_files = {
            item.name: item.read_bytes()
            for item in tmp_path.iterdir()
            if item.is_file()
        }
        assert set(original_files) == {
            "legacy.db",
            "legacy.db-wal",
            "legacy.db-shm",
        }
        database = Database(f"sqlite:///{path}")

        with pytest.raises(LegacyDatabaseError, match="v0.1"):
            reject_legacy_schema(database.engine)

        current_files = {
            item.name: item.read_bytes()
            for item in tmp_path.iterdir()
            if item.is_file()
        }
        assert current_files == original_files
    finally:
        connection.close()


def test_wal_snapshot_change_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE meetings (id TEXT PRIMARY KEY, project TEXT)")
        connection.commit()
        real_copyfile = schema_guard.copyfile

        def mutating_copyfile(source, destination):
            result = real_copyfile(source, destination)
            source_path = schema_guard.Path(source)
            if source_path == path:
                stat = source_path.stat()
                os.utime(
                    source_path,
                    ns=(stat.st_atime_ns, stat.st_mtime_ns + 1),
                )
            return result

        monkeypatch.setattr(schema_guard, "copyfile", mutating_copyfile)
        database = Database(f"sqlite:///{path}")

        with pytest.raises(LegacyDatabaseError, match="changed during inspection"):
            reject_legacy_schema(database.engine)
    finally:
        connection.close()
