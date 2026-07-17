from fastapi.testclient import TestClient

from app.main import create_app


def test_built_spa_is_served_for_root_and_client_routes(settings):
    settings.frontend_dist = settings.data_dir.parent / "frontend-dist"
    assets = settings.frontend_dist / "assets"
    assets.mkdir(parents=True)
    (settings.frontend_dist / "index.html").write_text(
        '<div id="app"></div><script src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("window.MEETFLOW = true", encoding="utf-8")

    with TestClient(create_app(settings)) as client:
        root = client.get("/")
        nested = client.get("/meetings/example-id")
        asset = client.get("/assets/app.js")
        missing_api = client.get("/api/not-a-real-endpoint")

    assert root.status_code == 200
    assert '<div id="app"></div>' in root.text
    assert nested.status_code == 200
    assert '<div id="app"></div>' in nested.text
    assert asset.status_code == 200
    assert asset.text == "window.MEETFLOW = true"
    assert missing_api.status_code == 404


def test_frontend_api_contract_smoke(authenticated_client):
    created = authenticated_client.post(
        "/api/meetings",
        json={
            "title": "Frontend contract",
            "project": "MeetFlow",
            "meeting_type": "integration",
            "meeting_date": "2026-07-17T13:30:00Z",
            "participants": ["Admin"],
            "raw_notes_markdown": "## Notes",
            "conclusions_markdown": "- Ship it",
        },
    )
    assert created.status_code == 201
    meeting_id = created.json()["id"]

    summaries = authenticated_client.get("/api/meetings?q=Frontend")
    package = authenticated_client.get(f"/api/meetings/{meeting_id}")
    action = authenticated_client.post(
        f"/api/meetings/{meeting_id}/actions",
        json={
            "content": "Verify integration",
            "owner": "Admin",
            "due_date": None,
            "status": "open",
        },
    )
    plugins = authenticated_client.get("/api/admin/plugins")

    assert summaries.status_code == 200
    assert summaries.json()[0]["open_action_count"] == 0
    assert summaries.json()[0]["attachment_count"] == 0
    assert package.status_code == 200
    assert package.json()["actions"] == []
    assert package.json()["attachments"] == []
    assert package.json()["updates"] == []
    assert action.status_code == 201
    assert action.json()["meeting_title"] == "Frontend contract"
    assert plugins.status_code == 200
    assert set(plugins.json()) == {"plugins", "errors"}
