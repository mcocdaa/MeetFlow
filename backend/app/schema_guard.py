import sqlite3
import tempfile
from pathlib import Path
from shutil import copyfile

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError


class LegacyDatabaseError(RuntimeError):
    pass


def _fingerprint(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


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


def _read_only_engine(path: Path) -> Engine:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    return create_engine(
        "sqlite://",
        creator=lambda: sqlite3.connect(uri, uri=True),
    )


def _reject_sqlite_wal_schema(path: Path, wal: Path, shm: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="meetflow-schema-guard-") as directory:
        snapshot = Path(directory) / path.name
        sources = (path, wal, shm)
        try:
            before = {source: _fingerprint(source) for source in sources}
            for source in sources:
                copyfile(source, snapshot.with_name(source.name))
            after = {source: _fingerprint(source) for source in sources}
        except OSError as exc:
            raise LegacyDatabaseError(
                "SQLite WAL changed during inspection; archive data/ and start fresh"
            ) from exc
        if before != after or not wal.is_file() or not shm.is_file():
            raise LegacyDatabaseError(
                "SQLite WAL changed during inspection; archive data/ and start fresh"
            )

        read_only_engine = _read_only_engine(snapshot)
        try:
            _reject_legacy_schema(read_only_engine)
        except SQLAlchemyError as exc:
            raise LegacyDatabaseError(
                "SQLite WAL could not be inspected safely; archive data/ and start fresh"
            ) from exc
        finally:
            read_only_engine.dispose()


def reject_legacy_schema(engine: Engine) -> None:
    database = engine.url.database
    if engine.dialect.name != "sqlite" or not database or database == ":memory:":
        _reject_legacy_schema(engine)
        return

    path = Path(database)
    if not path.is_file():
        return

    wal = path.with_name(f"{path.name}-wal")
    shm = path.with_name(f"{path.name}-shm")
    if wal.exists() != shm.exists():
        raise LegacyDatabaseError(
            "SQLite WAL is incomplete; archive data/ and start fresh"
        )
    if wal.exists():
        _reject_sqlite_wal_schema(path, wal, shm)
        return

    read_only_engine = _read_only_engine(path)
    try:
        _reject_legacy_schema(read_only_engine)
    finally:
        read_only_engine.dispose()
