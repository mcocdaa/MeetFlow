def login_admin(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200


def test_admin_approves_pending_user(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "display_name": "Alice",
            "password": "a-secure-member-pass",
        },
    )
    login_admin(client)
    pending = client.get("/api/admin/users?status=pending").json()

    response = client.post(f"/api/admin/users/{pending[0]['id']}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_admin_creates_active_demo_account(client):
    login_admin(client)

    response = client.post(
        "/api/admin/users",
        json={
            "username": "demo",
            "display_name": "Demo",
            "password": "fixed-demo-password",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "active"


def test_member_cannot_list_users(client):
    login_admin(client)
    created = client.post(
        "/api/admin/users",
        json={
            "username": "member",
            "display_name": "Member",
            "password": "member-password-123",
        },
    )
    assert created.status_code == 201
    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"username": "member", "password": "member-password-123"},
    ).status_code == 200

    response = client.get("/api/admin/users")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"


def test_disable_invalidates_member_session(client):
    login_admin(client)
    member = client.post(
        "/api/admin/users",
        json={
            "username": "member",
            "display_name": "Member",
            "password": "member-password-123",
        },
    ).json()
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"username": "member", "password": "member-password-123"},
    )
    member_cookie = client.cookies.get("meetflow_session")
    client.cookies.clear()
    login_admin(client)

    assert client.post(
        f"/api/admin/users/{member['id']}/disable"
    ).status_code == 200
    client.cookies.set("meetflow_session", member_cookie)
    assert client.get("/api/auth/me").status_code == 401


def test_admin_resets_member_password(client):
    login_admin(client)
    member = client.post(
        "/api/admin/users",
        json={
            "username": "member",
            "display_name": "Member",
            "password": "member-password-123",
        },
    ).json()

    response = client.post(
        f"/api/admin/users/{member['id']}/reset-password",
        json={"password": "member-new-password"},
    )

    assert response.status_code == 204
    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"username": "member", "password": "member-new-password"},
    ).status_code == 200
