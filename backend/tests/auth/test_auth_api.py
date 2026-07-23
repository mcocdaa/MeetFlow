def test_admin_can_login_and_read_session(client):
    login = client.post(
        "/api/auth/login",
        json={"username": "ADMIN", "password": "correct-horse-battery"},
    )

    assert login.status_code == 200
    assert login.json()["role"] == "admin"
    assert login.json()["avatar_color"] == "#64748b"
    current_user = client.get("/api/auth/me").json()
    assert current_user["username"] == "admin"
    assert current_user["avatar_color"] == "#64748b"


def test_session_endpoint_is_available_without_login(client):
    anonymous = client.get("/api/auth/session")

    assert anonymous.status_code == 200
    assert anonymous.json() == {"user": None}

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200

    authenticated = client.get("/api/auth/session")
    assert authenticated.status_code == 200
    assert authenticated.json()["user"]["username"] == "admin"


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
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).status_code
        == 200
    )

    changed = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "correct-horse-battery",
            "new_password": "a-new-secure-admin-pass",
        },
    )

    assert changed.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
