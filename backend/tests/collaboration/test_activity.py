import pytest
from sqlalchemy import select

from app.auth.models import User
from app.collaboration.models import ActivityEvent
from app.errors import AppError
from app.projects.models import Project
from app.projects.schemas import ProjectEdit
from app.projects.service import ProjectService


def _create_project(client, *, name: str, slug: str) -> dict:
    actor = client.get("/api/auth/me").json()
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "slug": slug,
            "status": "active",
            "lead_user_id": actor["id"],
            "member_ids": [actor["id"]],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_activity_is_committed_with_mutation_but_not_stale_failure(
    authenticated_client,
):
    actor = authenticated_client.get("/api/auth/me").json()
    project = _create_project(
        authenticated_client, name="Atomic activity", slug="atomic-activity"
    )

    activity = authenticated_client.get(f"/api/projects/{project['id']}/activity")
    assert activity.status_code == 200
    items = activity.json()["items"]
    assert items[0]["event_type"] == "project.created"
    assert items[0]["actor"]["id"] == actor["id"]
    assert items[0]["subject"] == {"type": "project", "id": project["id"]}

    database = authenticated_client.app.state.database
    with database.session() as stale, database.session() as winner:
        stale_actor = stale.get(User, actor["id"])
        winner_actor = winner.get(User, actor["id"])
        stale_project = ProjectService(stale).require(project["id"])
        assert stale_project.version == 1

        winner_project = ProjectService(winner).update(
            project["id"],
            ProjectEdit(expected_version=1, summary="Winner change"),
            winner_actor,
        )
        assert winner_project.version == 2

        with pytest.raises(AppError) as conflict:
            ProjectService(stale).update(
                project["id"],
                ProjectEdit(expected_version=1, summary="Stale change"),
                stale_actor,
            )
        assert conflict.value.code == "version_conflict"
        assert conflict.value.details == {
            "expected_version": 1,
            "actual_version": 2,
        }

    with database.session() as independent:
        persisted = independent.get(Project, project["id"])
        assert persisted.summary == "Winner change"
        assert persisted.version == 2
        events = list(
            independent.scalars(
                select(ActivityEvent)
                .where(ActivityEvent.project_id == project["id"])
                .order_by(ActivityEvent.id)
            )
        )
        assert [event.event_type for event in events] == [
            "project.created",
            "project.updated",
        ]
        assert all(event.payload_json["name"] == project["name"] for event in events)


def test_activity_api_is_project_scoped_and_gap_free(authenticated_client, client):
    first = _create_project(
        authenticated_client, name="First activity", slug="first-activity"
    )
    second = _create_project(
        authenticated_client, name="Second activity", slug="second-activity"
    )

    for content in ("First update", "Second update", "Third update"):
        response = authenticated_client.post(
            f"/api/projects/{first['id']}/updates",
            json={"health": "on_track", "content_markdown": content},
        )
        assert response.status_code == 201
    response = authenticated_client.post(
        f"/api/projects/{second['id']}/updates",
        json={"health": "at_risk", "content_markdown": "Other project"},
    )
    assert response.status_code == 201

    full = authenticated_client.get(
        f"/api/projects/{first['id']}/activity", params={"limit": 100}
    ).json()
    first_page = authenticated_client.get(
        f"/api/projects/{first['id']}/activity", params={"limit": 2}
    ).json()
    second_page = authenticated_client.get(
        f"/api/projects/{first['id']}/activity",
        params={"limit": 2, "before": first_page["next_cursor"]},
    ).json()

    full_ids = [item["id"] for item in full["items"]]
    paged_ids = [item["id"] for item in first_page["items"] + second_page["items"]]
    assert full_ids == sorted(full_ids, reverse=True)
    assert paged_ids == full_ids
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"] == first_page["items"][-1]["id"]
    assert second_page["next_cursor"] is None

    other = authenticated_client.get(f"/api/projects/{second['id']}/activity").json()
    assert {item["project_id"] for item in full["items"]} == {first["id"]}
    assert {item["project_id"] for item in other["items"]} == {second["id"]}

    actor = authenticated_client.get("/api/auth/me").json()
    secret = "PRIVATE-MARKDOWN-MUST-NOT-BE-RECORDED"
    action = authenticated_client.post(
        f"/api/projects/{first['id']}/actions",
        json={
            "project_id": first["id"],
            "content": secret,
            "owner_user_id": actor["id"],
        },
    )
    assert action.status_code == 201
    question = authenticated_client.post(
        f"/api/projects/{first['id']}/open-questions",
        json={"question_markdown": secret, "owner_user_id": actor["id"]},
    )
    assert question.status_code == 201
    attachment = authenticated_client.post(
        f"/api/attachments/project/{first['id']}",
        files={"file": ("evidence.txt", b"private file body", "text/plain")},
    )
    assert attachment.status_code == 201
    assert (
        authenticated_client.delete(attachment.json()["download_url"]).status_code
        == 204
    )

    latest = authenticated_client.get(
        f"/api/projects/{first['id']}/activity", params={"limit": 100}
    ).json()["items"]
    relevant = [
        item
        for item in latest
        if item["subject"]["id"]
        in {action.json()["id"], question.json()["id"], attachment.json()["id"]}
    ]
    assert {item["event_type"] for item in relevant} == {
        "action.created",
        "question.created",
        "attachment.uploaded",
        "attachment.deleted",
    }
    assert all(secret not in str(item["payload"]) for item in relevant)
    assert all("private file body" not in str(item["payload"]) for item in relevant)

    authenticated_client.post("/api/auth/logout")
    assert client.get(f"/api/projects/{first['id']}/activity").status_code == 401
