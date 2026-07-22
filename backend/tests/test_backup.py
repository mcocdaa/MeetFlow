import json
import sqlite3
from pathlib import Path

from scripts.backup import create_backup


def test_create_backup_copies_consistent_database_and_uploads(
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    database = data_dir / "meetflow.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE meetings (title TEXT NOT NULL)")
        connection.execute("INSERT INTO meetings VALUES ('Demo')")
        connection.commit()

    attachment = data_dir / "uploads" / "meeting-1" / "whiteboard.png"
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"png-data")

    destination = create_backup(
        database=database,
        uploads=data_dir / "uploads",
        output_dir=tmp_path / "backups",
        backup_name="20260717T180000Z",
    )

    with sqlite3.connect(destination / "meetflow.db") as connection:
        assert connection.execute("SELECT title FROM meetings").fetchone() == ("Demo",)
    assert (
        destination / "uploads" / "meeting-1" / "whiteboard.png"
    ).read_bytes() == b"png-data"
    assert json.loads((destination / "manifest.json").read_text()) == {
        "created_at": "2026-07-17T18:00:00+00:00",
        "database": "meetflow.db",
        "uploads": "uploads",
    }
