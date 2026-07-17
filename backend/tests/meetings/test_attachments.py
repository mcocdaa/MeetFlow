def test_upload_download_and_delete_image(authenticated_client, meeting_id):
    uploaded = authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={
            "file": (
                "board.png",
                b"\x89PNG\r\n\x1a\nimage",
                "image/png",
            )
        },
    )

    assert uploaded.status_code == 201
    attachment = uploaded.json()
    assert attachment["attachment_type"] == "image"
    assert attachment["created_by"]["username"] == "admin"
    assert authenticated_client.get("/api/meetings").json()[0][
        "attachment_count"
    ] == 1

    download = authenticated_client.get(
        f"/api/meetings/{meeting_id}/attachments/{attachment['id']}"
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("image/png")
    assert download.content.startswith(b"\x89PNG")

    deleted = authenticated_client.delete(
        f"/api/meetings/{meeting_id}/attachments/{attachment['id']}"
    )
    assert deleted.status_code == 204
    assert authenticated_client.get(f"/api/meetings/{meeting_id}").json()[
        "attachments"
    ] == []


def test_untrusted_content_type_is_downloaded_not_rendered(
    authenticated_client, meeting_id
):
    uploaded = authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={"file": ("page.html", b"<script>alert(1)</script>", "image/png")},
    ).json()

    response = authenticated_client.get(
        f"/api/meetings/{meeting_id}/attachments/{uploaded['id']}"
    )

    assert uploaded["attachment_type"] == "file"
    assert uploaded["mime_type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_oversized_upload_leaves_no_database_or_file(
    authenticated_client, meeting_id, settings
):
    authenticated_client.app.state.attachment_storage.max_bytes = 8

    response = authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={"file": ("too-big.txt", b"123456789", "text/plain")},
    )

    assert response.status_code == 413
    assert not any(
        path.is_file() for path in (settings.data_dir / "uploads").rglob("*")
    )
    assert authenticated_client.get(f"/api/meetings/{meeting_id}").json()[
        "attachments"
    ] == []


def test_deleting_meeting_removes_attachment_directory(
    authenticated_client, meeting_id, settings
):
    uploaded = authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )
    assert uploaded.status_code == 201

    assert authenticated_client.delete(
        f"/api/meetings/{meeting_id}"
    ).status_code == 204
    assert not (settings.data_dir / "uploads" / meeting_id).exists()


def test_attachment_id_must_belong_to_meeting(
    authenticated_client, meeting_id
):
    other = authenticated_client.post(
        "/api/meetings",
        json={
            "title": "Other meeting",
            "project": "MeetFlow",
            "meeting_type": "technical",
            "meeting_date": "2026-07-18T13:30:00Z",
            "participants": [],
            "raw_notes_markdown": "",
            "conclusions_markdown": "",
        },
    ).json()["id"]
    uploaded = authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={"file": ("notes.txt", b"notes", "text/plain")},
    ).json()

    response = authenticated_client.get(
        f"/api/meetings/{other}/attachments/{uploaded['id']}"
    )

    assert response.status_code == 404
