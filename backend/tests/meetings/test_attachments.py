from sqlalchemy import select
from sqlalchemy.orm import Session

import pytest

from app.attachments.models import Attachment
from app.collaboration.activity import ActivityRecorder
from app.collaboration.models import ActivityEvent


def upload(client, meeting_id, name="board.png", content=b"\x89PNG\r\n\x1a\nimage"):
    return client.post(
        f"/api/attachments/meeting/{meeting_id}",
        files={"file": (name, content, "image/png")},
    )


def test_upload_download_preview_and_delete(authenticated_client, meeting_id):
    response = upload(authenticated_client, meeting_id)
    assert response.status_code == 201
    attachment = response.json()
    assert attachment["attachment_type"] == "image"
    assert attachment["created_by"]["username"] == "admin"

    download = authenticated_client.get(attachment["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("image/png")
    assert download.headers["x-content-type-options"] == "nosniff"

    text = authenticated_client.post(
        f"/api/attachments/meeting/{meeting_id}",
        files={"file": ("notes.md", b"# Notes", "text/markdown")},
    ).json()
    preview = authenticated_client.get(text["preview_url"])
    assert preview.status_code == 200
    assert preview.text == "# Notes"
    assert preview.headers["x-content-type-options"] == "nosniff"

    assert authenticated_client.delete(attachment["download_url"]).status_code == 204
    assert (
        len(authenticated_client.get(f"/api/attachments/meeting/{meeting_id}").json())
        == 1
    )


def test_target_and_attachment_ids_cannot_escape_storage(
    authenticated_client, meeting_id
):
    attachment = upload(authenticated_client, meeting_id).json()
    assert (
        authenticated_client.get(
            f"/api/attachments/project/{meeting_id}/{attachment['id']}"
        ).status_code
        == 404
    )
    assert authenticated_client.post(
        "/api/attachments/meeting/..",
        files={"file": ("x.txt", b"x", "text/plain")},
    ).status_code in {404, 405}


def test_delete_removes_metadata_when_file_is_already_missing(
    authenticated_client, meeting_id
):
    item = upload(authenticated_client, meeting_id).json()
    database = authenticated_client.app.state.database
    with database.session() as session:
        attachment = session.get(Attachment, item["id"])
        path = authenticated_client.app.state.attachment_storage.attachment_path(
            attachment.target_type, attachment.target_id, attachment.stored_name
        )
        path.unlink()

    response = authenticated_client.delete(item["download_url"])
    assert response.status_code == 204
    with database.session() as session:
        assert session.get(Attachment, item["id"]) is None
        assert session.scalar(select(Attachment.id)) is None


def test_delete_commit_failure_restores_file_and_row(
    authenticated_client, meeting_id, monkeypatch
):
    item = upload(authenticated_client, meeting_id).json()
    database = authenticated_client.app.state.database
    with database.session() as session:
        attachment = session.get(Attachment, item["id"])
        original_path = (
            authenticated_client.app.state.attachment_storage.attachment_path(
                attachment.target_type, attachment.target_id, attachment.stored_name
            )
        )

    original_record = ActivityRecorder.record
    saw_pending_event = False

    def fail_activity_record(recorder, **values):
        nonlocal saw_pending_event
        event = original_record(recorder, **values)
        saw_pending_event = isinstance(event, ActivityEvent)
        raise RuntimeError("activity unavailable")

    monkeypatch.setattr(ActivityRecorder, "record", fail_activity_record)
    with pytest.raises(RuntimeError, match="activity unavailable"):
        authenticated_client.delete(item["download_url"])
    monkeypatch.setattr(ActivityRecorder, "record", original_record)

    assert saw_pending_event
    assert original_path.is_file()
    assert not list(original_path.parent.glob(".delete-*"))
    with database.session() as session:
        assert session.get(Attachment, item["id"]) is not None
        assert (
            session.scalar(
                select(ActivityEvent.id).where(
                    ActivityEvent.event_type == "attachment.deleted",
                    ActivityEvent.subject_id == item["id"],
                )
            )
            is None
        )

    original_commit = Session.commit
    saw_event_at_commit = False

    def fail_commit(session):
        nonlocal saw_event_at_commit
        saw_event_at_commit = any(
            isinstance(value, ActivityEvent)
            and value.event_type == "attachment.deleted"
            and value.subject_id == item["id"]
            for value in session.new
        )
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="database unavailable"):
        authenticated_client.delete(item["download_url"])
    monkeypatch.setattr(Session, "commit", original_commit)

    assert saw_event_at_commit
    assert original_path.is_file()
    assert not list(original_path.parent.glob(".delete-*"))
    with database.session() as session:
        assert session.get(Attachment, item["id"]) is not None
        assert (
            session.scalar(
                select(ActivityEvent.id).where(
                    ActivityEvent.event_type == "attachment.deleted",
                    ActivityEvent.subject_id == item["id"],
                )
            )
            is None
        )
        session.commit()


def test_delete_unlink_failure_keeps_tombstone_and_returns_204(
    authenticated_client, meeting_id, monkeypatch, caplog
):
    item = upload(authenticated_client, meeting_id).json()
    database = authenticated_client.app.state.database
    with database.session() as session:
        attachment = session.get(Attachment, item["id"])
        original_path = (
            authenticated_client.app.state.attachment_storage.attachment_path(
                attachment.target_type, attachment.target_id, attachment.stored_name
            )
        )

    path_type = type(original_path)
    original_unlink = path_type.unlink

    def fail_tombstone_unlink(path, *args, **kwargs):
        if path.name.startswith(".delete-"):
            raise OSError("disk busy")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(path_type, "unlink", fail_tombstone_unlink)
    with caplog.at_level("WARNING"):
        response = authenticated_client.delete(item["download_url"])

    assert response.status_code == 204
    assert not original_path.exists()
    tombstones = list(original_path.parent.glob(".delete-*"))
    assert len(tombstones) == 1
    assert "attachment tombstone cleanup failed" in caplog.text
    with database.session() as session:
        assert session.get(Attachment, item["id"]) is None
