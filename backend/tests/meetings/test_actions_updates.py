def test_actions_are_attributed_editable_and_aggregated(
    authenticated_client, meeting_id
):
    action = authenticated_client.post(
        f"/api/meetings/{meeting_id}/actions",
        json={
            "content": "调研数据集",
            "owner": "我",
            "due_date": "2026-07-20",
            "status": "open",
        },
    )

    assert action.status_code == 201
    assert action.json()["created_by"]["username"] == "admin"
    action_id = action.json()["id"]
    assert authenticated_client.get("/api/meetings").json()[0][
        "open_action_count"
    ] == 1
    assert authenticated_client.get("/api/meetings").json()[0][
        "action_count"
    ] == 1
    assert len(authenticated_client.get("/api/actions?status=open").json()) == 1

    completed = authenticated_client.put(
        f"/api/meetings/{meeting_id}/actions/{action_id}",
        json={
            "content": "调研数据集",
            "owner": "我",
            "due_date": "2026-07-20",
            "status": "done",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "done"
    assert authenticated_client.get("/api/actions?status=open").json() == []
    summary = authenticated_client.get("/api/meetings").json()[0]
    assert summary["action_count"] == 1
    assert summary["open_action_count"] == 0

    assert authenticated_client.delete(
        f"/api/meetings/{meeting_id}/actions/{action_id}"
    ).status_code == 204


def test_meeting_updates_are_attributed_and_deletable(
    authenticated_client, meeting_id
):
    update = authenticated_client.post(
        f"/api/meetings/{meeting_id}/updates",
        json={"content_markdown": "完成第一轮数据加载测试。"},
    )

    assert update.status_code == 201
    assert update.json()["created_by"]["username"] == "admin"
    update_id = update.json()["id"]
    package = authenticated_client.get(f"/api/meetings/{meeting_id}").json()
    assert package["updates"][0]["content_markdown"].startswith("完成")

    assert authenticated_client.delete(
        f"/api/meetings/{meeting_id}/updates/{update_id}"
    ).status_code == 204


def test_child_id_must_belong_to_meeting(authenticated_client, meeting_id):
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
    action = authenticated_client.post(
        f"/api/meetings/{meeting_id}/actions",
        json={"content": "Scoped action", "status": "open"},
    ).json()

    response = authenticated_client.put(
        f"/api/meetings/{other}/actions/{action['id']}",
        json={"content": "Moved action", "status": "open"},
    )

    assert response.status_code == 404


def test_invalid_global_action_status_is_rejected(authenticated_client):
    response = authenticated_client.get("/api/actions?status=typo")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
