#!/usr/bin/env python3
"""Create a SQLite-safe MeetFlow backup with uploaded files."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _created_at(backup_name: str) -> datetime:
    try:
        return datetime.strptime(
            backup_name, "%Y%m%dT%H%M%SZ"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def create_backup(
    *,
    database: Path,
    uploads: Path,
    output_dir: Path,
    backup_name: str | None = None,
) -> Path:
    """Back up SQLite through its online backup API, then copy uploads."""
    database = database.resolve()
    uploads = uploads.resolve()
    output_dir = output_dir.resolve()
    if not database.is_file():
        raise FileNotFoundError(f"database does not exist: {database}")

    name = backup_name or datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("backup name must be a single directory name")

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / name
    if destination.exists():
        raise FileExistsError(f"backup already exists: {destination}")

    temporary = output_dir / f".{name}.{uuid.uuid4().hex}.tmp"
    temporary.mkdir()
    try:
        target_database = temporary / "meetflow.db"
        with sqlite3.connect(database) as source, sqlite3.connect(
            target_database
        ) as target:
            source.backup(target)

        if uploads.is_dir():
            shutil.copytree(uploads, temporary / "uploads")
        else:
            (temporary / "uploads").mkdir()

        manifest = {
            "created_at": _created_at(name).isoformat(),
            "database": "meetflow.db",
            "uploads": "uploads",
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/meetflow.db")
    )
    parser.add_argument("--uploads", type=Path, default=Path("data/uploads"))
    parser.add_argument("--output", type=Path, default=Path("backups"))
    parser.add_argument("--name", help="explicit backup directory name")
    args = parser.parse_args()
    destination = create_backup(
        database=args.database,
        uploads=args.uploads,
        output_dir=args.output,
        backup_name=args.name,
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
