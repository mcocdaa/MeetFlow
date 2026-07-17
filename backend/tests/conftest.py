from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "data",
        plugins_dir=tmp_path / "plugins",
        admin_username="admin",
        admin_password="correct-horse-battery",
        app_secret_key="test-secret-key-with-at-least-32-chars",
        allow_registration=True,
        secure_cookies=False,
    )


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def meeting_id(authenticated_client):
    response = authenticated_client.post(
        "/api/meetings",
        json={
            "title": "Fixture meeting",
            "project": "MeetFlow",
            "meeting_type": "technical",
            "meeting_date": "2026-07-17T13:30:00Z",
            "participants": ["Admin"],
            "raw_notes_markdown": "Fixture notes",
            "conclusions_markdown": "Fixture conclusion",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]
