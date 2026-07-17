def login_admin(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200


def meeting_payload() -> dict:
    return {
        "title": "GRPO 数据集方案讨论",
        "project": "LLM Post-training",
        "meeting_type": "技术讨论",
        "meeting_date": "2026-07-17T13:30:00Z",
        "participants": ["张三", "李四", "我"],
        "raw_notes_markdown": "- AppWorld 数据完整",
        "conclusions_markdown": "1. 第一阶段使用 AppWorld",
    }


def test_meetings_require_authentication(client):
    response = client.get("/api/meetings")

    assert response.status_code == 401


def test_create_get_search_update_and_delete_meeting(client):
    login_admin(client)
    payload = meeting_payload()

    created = client.post("/api/meetings", json=payload)

    assert created.status_code == 201
    meeting_id = created.json()["id"]
    assert created.json()["created_by"]["username"] == "admin"
    assert created.json()["updated_by"]["username"] == "admin"

    package = client.get(f"/api/meetings/{meeting_id}")
    assert package.status_code == 200
    assert package.json()["title"] == payload["title"]
    assert package.json()["actions"] == []
    assert package.json()["attachments"] == []
    assert package.json()["updates"] == []

    matches = client.get("/api/meetings?q=grpo").json()
    assert len(matches) == 1
    assert matches[0]["open_action_count"] == 0
    assert matches[0]["attachment_count"] == 0
    assert matches[0]["conclusion_count"] == 1
    assert client.get("/api/meetings?q=post-training").json()[0]["id"] == meeting_id

    updated = client.put(
        f"/api/meetings/{meeting_id}",
        json={**payload, "title": "GRPO 方案复盘"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "GRPO 方案复盘"

    assert client.delete(f"/api/meetings/{meeting_id}").status_code == 204
    assert client.get(f"/api/meetings/{meeting_id}").status_code == 404
