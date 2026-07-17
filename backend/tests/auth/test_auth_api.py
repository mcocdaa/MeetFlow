def test_admin_can_login_and_read_session(client):
    login = client.post(
        "/api/auth/login",
        json={"username": "ADMIN", "password": "correct-horse-battery"},
    )

    assert login.status_code == 200
    assert login.json()["role"] == "admin"
    assert client.get("/api/auth/me").json()["username"] == "admin"


def test_registration_creates_pending_user_without_logging_in(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "Alice",
            "display_name": "Alice",
            "password": "a-secure-member-pass",
        },
    )

    assert response.status_code == 201
    assert response.json() == {"status": "pending"}
    assert client.get("/api/auth/me").status_code == 401

    pending_login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "a-secure-member-pass"},
    )
    assert pending_login.status_code == 403
    assert pending_login.json()["error"]["code"] == "account_pending"


def test_duplicate_username_is_rejected_case_insensitively(client):
    payload = {
        "username": "Alice",
        "display_name": "Alice",
        "password": "a-secure-member-pass",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201

    duplicate = client.post(
        "/api/auth/register", json={**payload, "username": " alice "}
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "username_taken"


def test_registration_rejects_blank_normalized_identity(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "   ",
            "display_name": "   ",
            "password": "a-secure-member-pass",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_closed_registration_is_advertised_and_rejected(client, settings):
    settings.allow_registration = False

    assert client.get("/api/auth/config").json() == {"allow_registration": False}
    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "display_name": "Alice",
            "password": "a-secure-member-pass",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "registration_closed"


def test_cross_origin_write_is_rejected(client):
    response = client.post(
        "/api/auth/login",
        headers={"Origin": "https://evil.example"},
        json={"username": "admin", "password": "correct-horse-battery"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_forbidden"


def test_password_change_invalidates_existing_cookie(client):
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery"},
    ).status_code == 200

    changed = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "correct-horse-battery",
            "new_password": "a-new-secure-admin-pass",
        },
    )

    assert changed.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
