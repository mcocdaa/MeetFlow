import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect


class LegacyDatabaseError(RuntimeError):
    pass


def _reject_legacy_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "meetings" not in tables or "alembic_version" in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("meetings")}
    if "project" in columns and "project_id" not in columns:
        raise LegacyDatabaseError(
            "MeetFlow v0.1 database detected; archive data/ and start fresh"
        )


def reject_legacy_schema(engine: Engine) -> None:
    database = engine.url.database
    if engine.dialect.name != "sqlite" or not database or database == ":memory:":
        _reject_legacy_schema(engine)
        return

    path = Path(database)
    if not path.is_file():
        return

    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    read_only_engine = create_engine(
        "sqlite://",
        creator=lambda: sqlite3.connect(uri, uri=True),
    )
    try:
        _reject_legacy_schema(read_only_engine)
    finally:
        read_only_engine.dispose()
