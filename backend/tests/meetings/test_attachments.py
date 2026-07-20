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


def test_untrusted_content_type_is_downloaded_not_rendered(
    authenticated_client, meeting_id
):
    attachment = upload(
        authenticated_client,
        meeting_id,
        "page.html",
        b"<script>alert(1)</script>",
    ).json()
    response = authenticated_client.get(attachment["download_url"])
    assert attachment["attachment_type"] == "file"
    assert attachment["mime_type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert authenticated_client.get(attachment["preview_url"]).status_code == 415


def test_oversized_upload_is_atomic(authenticated_client, meeting_id, settings):
    authenticated_client.app.state.attachment_storage.max_bytes = 8
    response = upload(authenticated_client, meeting_id, "large.txt", b"123456789")
    assert response.status_code == 413
    assert not any(
        path.is_file() for path in (settings.data_dir / "uploads").rglob("*")
    )
    assert (
        authenticated_client.get(f"/api/attachments/meeting/{meeting_id}").json() == []
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
