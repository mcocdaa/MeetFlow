from datetime import date, datetime, timedelta, timezone


def create_workspace(client):
    user = client.get("/api/auth/me").json()
    project = client.post(
        "/api/projects",
        json={
            "name": "Workspace",
            "slug": "workspace",
            "status": "active",
            "lead_user_id": user["id"],
            "member_ids": [user["id"]],
        },
    ).json()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    meeting = client.post(
        f"/api/projects/{project['id']}/meetings",
        json={
            "title": "Planning",
            "scheduled_start": start.isoformat(),
            "scheduled_end": (start + timedelta(hours=1)).isoformat(),
            "host_user_id": user["id"],
            "participants": [{"user_id": user["id"], "participation_role": "host"}],
        },
    ).json()
    agenda = client.post(
        f"/api/meetings/{meeting['id']}/agenda-items",
        params={"expected_meeting_version": meeting["version"]},
        json={"title": "Release", "agenda_type": "decision"},
    ).json()
    return user, project, meeting, agenda


def test_targeted_attachments_and_nested_meeting_detail(authenticated_client):
    user, project, meeting, agenda = create_workspace(authenticated_client)
    for target_type, target_id in (
        ("project", project["id"]),
        ("meeting", meeting["id"]),
        ("agenda_item", agenda["id"]),
    ):
        response = authenticated_client.post(
            f"/api/attachments/{target_type}/{target_id}",
            files={"file": (f"{target_type}.txt", b"evidence", "text/plain")},
        )
        assert response.status_code == 201
        assert response.json()["target_type"] == target_type

    decision = authenticated_client.post(
        f"/api/projects/{project['id']}/decisions",
        json={
            "meeting_id": meeting["id"],
            "agenda_item_id": agenda["id"],
            "title": "Ship",
            "decision_markdown": "Release now",
        },
    )
    assert decision.status_code == 201
    action = authenticated_client.post(
        f"/api/projects/{project['id']}/actions",
        json={
            "project_id": project["id"],
            "meeting_id": meeting["id"],
            "agenda_item_id": agenda["id"],
            "content": "Publish image",
            "owner_user_id": user["id"],
            "due_date": (date.today() + timedelta(days=2)).isoformat(),
        },
    )
    assert action.status_code == 201

    detail = authenticated_client.get(f"/api/meetings/{meeting['id']}").json()
    assert len(detail["attachments"]) == 1
    assert len(detail["agenda_items"][0]["attachments"]) == 1
    assert detail["agenda_items"][0]["decisions"][0]["title"] == "Ship"
    assert detail["agenda_items"][0]["actions"][0]["content"] == "Publish image"


def test_invalid_attachment_target_does_not_write_file(authenticated_client, settings):
    response = authenticated_client.post(
        "/api/attachments/project/missing",
        files={"file": ("x.txt", b"not stored", "text/plain")},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "attachment_target_not_found"
    assert not list((settings.data_dir / "uploads").rglob("*"))


def test_workspace_views_require_authentication(client):
    assert client.get("/api/actions").status_code == 401
    assert client.get("/api/attention").status_code == 401
    assert client.get("/api/attachments/project/x").status_code == 401
