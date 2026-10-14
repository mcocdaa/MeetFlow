def test_api_key_lifecycle_and_headless_auth(authenticated_client, client, meeting_id):
    # 1. Fetch personal API key via browser session
    res = authenticated_client.get("/api/v1/auth/api-key")
    assert res.status_code == 200
    data = res.json()
    api_key = data["api_key"]
    assert api_key.startswith(f"mf_{data['user_id']}_")
    assert data["username"] == "admin"

    # 2. Authenticate headless client (no cookies) using X-API-Key and Authorization: Bearer
    me_res = client.get(
        "/api/auth/me",
        cookies={},
        headers={"X-API-Key": api_key},
    )
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "admin"

    bearer_res = client.get(
        "/api/meetings/" + meeting_id,
        cookies={},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert bearer_res.status_code == 200
    assert bearer_res.json()["id"] == meeting_id

    # 3. Rotate API key: old key must be invalidated immediately, new key works, browser cookie remains valid
    rot_res = authenticated_client.post("/api/v1/auth/api-key/rotate")
    assert rot_res.status_code == 200
    new_key = rot_res.json()["api_key"]
    assert new_key != api_key
    assert new_key.startswith(f"mf_{data['user_id']}_")

    old_check = client.get(
        "/api/auth/me",
        cookies={},
        headers={"X-API-Key": api_key},
    )
    assert old_check.status_code == 401

    new_check = client.get(
        "/api/auth/me",
        cookies={},
        headers={"X-API-Key": new_key},
    )
    assert new_check.status_code == 200

    # Browser session cookie was refreshed during rotate
    assert authenticated_client.get("/api/auth/me").status_code == 200


def test_atomic_meeting_notes_ingestion_via_api_key(authenticated_client, client, meeting_id):
    api_key = authenticated_client.get("/api/v1/auth/api-key").json()["api_key"]

    # 1. Ingest notes without agenda_item_id -> creates new agenda item and extracts outcomes
    ingest_res = client.post(
        f"/api/v1/meetings/{meeting_id}/ingest",
        cookies={},
        headers={"X-API-Key": api_key},
        json={
            "agenda_title": "AI 架构评审纪要",
            "notes_markdown": (
                "### 核心结论\n"
                "@决策: 统一采用单源 Canonical API 架构\n"
                "@决策: 支持 X-API-Key 无头鉴权\n"
                "@行动:[in_progress][@admin][2026-10-25] 完成自动化回归测试\n"
                "@开放问题: 是否开启跨项目 Webhook 汇总？\n"
            ),
            "auto_complete_agenda": False,
        },
    )
    assert ingest_res.status_code == 200
    body = ingest_res.json()
    assert body["decisions"] == 2
    assert body["actions"] == 1
    assert body["questions"] == 1
    assert body["extracted"] == {"decisions": 2, "actions": 1, "questions": 1}

    agenda_id = body["ingested_agenda_item_id"]
    agenda_items = [a for a in body["agenda_items"] if a["id"] == agenda_id]
    assert len(agenda_items) == 1
    agenda = agenda_items[0]
    assert agenda["title"] == "AI 架构评审纪要"
    assert agenda["status"] == "planned"
    assert len(agenda["decisions"]) == 2
    assert len(agenda["actions"]) == 1
    assert agenda["actions"][0]["content"] == "完成自动化回归测试"
    assert agenda["actions"][0]["status"] == "in_progress"
    assert len(agenda["open_questions"]) == 1
    assert agenda["open_questions"][0]["question_markdown"] == "是否开启跨项目 Webhook 汇总？"

    # 2. Update the existing agenda item by agenda_item_id and auto_complete_agenda=True
    update_res = client.post(
        f"/api/v1/meetings/{meeting_id}/ingest",
        cookies={},
        headers={"X-API-Key": api_key},
        json={
            "agenda_item_id": agenda_id,
            "notes_markdown": (
                "@决策: 统一采用单源 Canonical API 架构\n"
                "@行动:[done][@admin][2026-10-25] 完成自动化回归测试\n"
            ),
            "auto_complete_agenda": True,
        },
    )
    assert update_res.status_code == 200
    updated_body = update_res.json()
    assert updated_body["decisions"] == 1
    assert updated_body["actions"] == 1
    assert updated_body["questions"] == 0

    updated_agenda = next(
        a for a in updated_body["agenda_items"] if a["id"] == agenda_id
    )
    assert updated_agenda["status"] == "completed"
    assert len(updated_agenda["decisions"]) == 1
    assert len(updated_agenda["actions"]) == 1
    assert updated_agenda["actions"][0]["status"] == "done"
    assert len(updated_agenda["open_questions"]) == 0
