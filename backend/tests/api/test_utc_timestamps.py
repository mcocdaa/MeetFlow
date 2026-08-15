import re

from tests.conftest import create_plugin_meeting


DATETIME_STRING = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)


def _assert_no_naive_datetimes(payload):
    if isinstance(payload, dict):
        for value in payload.values():
            _assert_no_naive_datetimes(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_naive_datetimes(item)
    elif isinstance(payload, str):
        match = DATETIME_STRING.search(payload)
        if match and match.group(2) is None:
            raise AssertionError(f"naive datetime string in response: {payload!r}")


def test_non_meeting_endpoints_render_utc_z_timestamps(plugin_client):
    """Projects, outcomes, attachments, comments and attention all emit Z-UTC."""
    client = plugin_client
    user = client.get("/api/auth/me").json()
    project = client.post(
        "/api/projects",
        json={
            "name": "Timestamps",
            "slug": "timestamps",
            "status": "active",
            "lead_user_id": user["id"],
            "member_ids": [user["id"]],
        },
    ).json()
    meeting_id = create_plugin_meeting(client)

    project_detail = client.get(f"/api/projects/{project['id']}").json()
    _assert_no_naive_datetimes(project_detail)
    assert project_detail["updated_at"].endswith("Z")

    decisions = client.post(
        f"/api/projects/{project['id']}/decisions",
        json={
            "meeting_id": meeting_id,
            "title": "Ship",
            "decision_markdown": "Release",
        },
    ).json()
    _assert_no_naive_datetimes(decisions)

    uploaded = client.post(
        f"/api/attachments/meeting/{meeting_id}",
        files={"file": ("t.txt", b"evidence", "text/plain")},
    ).json()
    assert uploaded["created_at"].endswith("Z")

    comments = client.post(
        "/api/comments",
        json={
            "target_type": "meeting",
            "target_id": meeting_id,
            "body_markdown": "Note",
        },
    ).json()
    assert comments["created_at"].endswith("Z")

    attention = client.get("/api/attention").json()
    _assert_no_naive_datetimes(attention)

    inbox = client.get("/api/inbox").json()
    _assert_no_naive_datetimes(inbox)

    activity = client.get(f"/api/projects/{project['id']}/activity").json()
    _assert_no_naive_datetimes(activity)
