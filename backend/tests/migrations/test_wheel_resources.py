import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_RESOURCES = {
    "share/meetflow/alembic.ini",
    "share/meetflow/migrations/env.py",
    "share/meetflow/migrations/script.py.mako",
} | {
    f"share/meetflow/migrations/versions/{path.name}"
    for path in (PROJECT_ROOT / "backend" / "migrations" / "versions").glob("*.py")
}


def test_wheel_contains_and_runs_migrations_outside_source_tree(tmp_path):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PIP_ROOT_USER_ACTION": "ignore",
        }
    )
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", source / "pyproject.toml")
    shutil.copytree(PROJECT_ROOT / "backend", source / "backend")
    wheelhouse = tmp_path / "wheelhouse"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheelhouse),
        ],
        cwd=source,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    wheel = next(wheelhouse.glob("meetflow-*.whl"))
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
    for resource in MIGRATION_RESOURCES:
        assert any(name.endswith(resource) for name in names), resource

    virtualenv = tmp_path / "venv"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "venv",
            "--system-site-packages",
            str(virtualenv),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    virtualenv_python = virtualenv / "bin" / "python"
    subprocess.run(
        [
            str(virtualenv_python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            str(wheel),
        ],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    database = tmp_path / "installed.db"
    script = """
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.database import Database, migration_config_path
from sqlalchemy import inspect, text

database = Database(%r)
database.migrate()
assert %r <= set(inspect(database.engine).get_table_names())
columns = {
    table: {column["name"] for column in inspect(database.engine).get_columns(table)}
    for table in ("meeting_series", "meetings", "agenda_items", "decisions", "action_items", "open_questions")
}
assert {"recurrence_frequency", "recurrence_local_time", "recurrence_timezone"} <= columns["meeting_series"]
assert {"occurrence_kind", "series_slot_at"} <= columns["meetings"]
assert "actual_duration_seconds" in columns["agenda_items"]
for table in ("decisions", "action_items", "open_questions"):
    assert {"source_agenda_item_id", "source_tag_key"} <= columns[table]
with database.engine.connect() as connection:
    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == ScriptDirectory.from_config(
        Config(migration_config_path())
    ).get_current_head()
""" % (
        f"sqlite:///{database}",
        {
            "action_items",
            "activity_events",
            "agenda_items",
            "alembic_version",
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
            "users",
        },
    )
    run_directory = tmp_path / "outside-source"
    run_directory.mkdir()
    subprocess.run(
        [str(virtualenv_python), "-c", script],
        cwd=run_directory,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert not any(name.startswith("tests/") for name in names)
    assert not any(name.startswith("migrations/") for name in names)
