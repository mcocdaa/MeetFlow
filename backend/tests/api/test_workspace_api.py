from datetime import date, datetime, timedelta, timezone

from sqlalchemy import event, select

from app.auth.models import User, UserRole, UserStatus
from app.meetings.models import Meeting, MeetingAmendment, MeetingSnapshot
from app.meetings.service import MeetingService
from app.outcomes.models import Decision


def create_workspace(client):
    user = client.get("/api/auth/me").json()
    project = client.post(
        "/api/projects",
        json={
            "name": "Workspace",
            "slug": "workspace",
            "status": "active",
            "lead_user_id": user["id"],
            "member_ids": [user["id"]],
        },
    ).json()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    meeting = client.post(
        f"/api/projects/{project['id']}/meetings",
        json={
            "title": "Planning",
            "scheduled_start": start.isoformat(),
            "scheduled_end": (start + timedelta(hours=1)).isoformat(),
            "host_user_id": user["id"],
            "participants": [{"user_id": user["id"], "participation_role": "host"}],
        },
    ).json()
    agenda = client.post(
        f"/api/meetings/{meeting['id']}/agenda-items",
        params={"expected_meeting_version": meeting["version"]},
        json={"title": "Release", "agenda_type": "decision"},
    ).json()
    return user, project, meeting, agenda


def test_targeted_attachments_and_nested_meeting_detail(authenticated_client):
    user, project, meeting, agenda = create_workspace(authenticated_client)
    for target_type, target_id in (
        ("project", project["id"]),
        ("meeting", meeting["id"]),
        ("agenda_item", agenda["id"]),
    ):
        response = authenticated_client.post(
            f"/api/attachments/{target_type}/{target_id}",
            files={"file": (f"{target_type}.txt", b"evidence", "text/plain")},
        )
        assert response.status_code == 201
        assert response.json()["target_type"] == target_type

    decision = authenticated_client.post(
        f"/api/projects/{project['id']}/decisions",
        json={
            "meeting_id": meeting["id"],
            "agenda_item_id": agenda["id"],
            "title": "Ship",
            "decision_markdown": "Release now",
        },
    )
    assert decision.status_code == 201
    action = authenticated_client.post(
        f"/api/projects/{project['id']}/actions",
        json={
            "project_id": project["id"],
            "meeting_id": meeting["id"],
            "agenda_item_id": agenda["id"],
            "content": "Publish image",
            "owner_user_id": user["id"],
            "due_date": (date.today() + timedelta(days=2)).isoformat(),
        },
    )
    assert action.status_code == 201

    detail = authenticated_client.get(f"/api/meetings/{meeting['id']}").json()
    assert len(detail["attachments"]) == 1
    assert len(detail["agenda_items"][0]["attachments"]) == 1
    assert detail["agenda_items"][0]["decisions"][0]["title"] == "Ship"
    assert detail["agenda_items"][0]["actions"][0]["content"] == "Publish image"


def test_invalid_attachment_target_does_not_write_file(authenticated_client, settings):
    response = authenticated_client.post(
        "/api/attachments/project/missing",
        files={"file": ("x.txt", b"not stored", "text/plain")},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "attachment_target_not_found"
    assert not list((settings.data_dir / "uploads").rglob("*"))


def test_project_overview_global_filters_and_attention(authenticated_client):
    user, project, meeting, agenda = create_workspace(authenticated_client)
    action = authenticated_client.post(
        f"/api/projects/{project['id']}/actions",
        json={
            "project_id": project["id"],
            "meeting_id": meeting["id"],
            "agenda_item_id": agenda["id"],
            "content": "Prepare",
            "owner_user_id": user["id"],
            "due_date": (date.today() + timedelta(days=1)).isoformat(),
        },
    ).json()

    overview = authenticated_client.get(f"/api/projects/{project['id']}").json()
    assert overview["next_meeting"]["id"] == meeting["id"]
    assert overview["open_action_count"] == 1
    assert overview["attachments"] == []

    actions = authenticated_client.get(
        "/api/actions",
        params={"project_id": project["id"], "owner_user_id": user["id"], "limit": 1},
    )
    assert actions.status_code == 200
    assert actions.json()["items"][0]["id"] == action["id"]
    assert actions.json()["total"] == 1
    assert (
        authenticated_client.get("/api/actions", params={"limit": 201}).status_code
        == 422
    )

    attention = authenticated_client.get("/api/attention").json()["items"]
    subjects = [(item["subject_type"], item["subject_id"]) for item in attention]
    assert len(subjects) == len(set(subjects))
    action_row = next(item for item in attention if item["subject_id"] == action["id"])
    assert action_row["reasons"] == ["action_due_soon"]
    meeting_row = next(
        item for item in attention if item["subject_id"] == meeting["id"]
    )
    assert set(meeting_row["reasons"]) == {
        "meeting_upcoming",
        "meeting_needs_preparation",
    }


def test_workspace_views_require_authentication(client):
    assert client.get("/api/actions").status_code == 401
    assert client.get("/api/attention").status_code == 401
    assert client.get("/api/attachments/project/x").status_code == 401


def test_agenda_with_attachment_cannot_be_deleted(authenticated_client):
    _, _, meeting, agenda = create_workspace(authenticated_client)
    authenticated_client.post(
        f"/api/attachments/agenda_item/{agenda['id']}",
        files={"file": ("evidence.txt", b"evidence", "text/plain")},
    )
    current = authenticated_client.get(f"/api/meetings/{meeting['id']}").json()
    response = authenticated_client.request(
        "DELETE",
        f"/api/agenda-items/{agenda['id']}",
        params={"expected_meeting_version": current["version"]},
        json={"expected_version": agenda["version"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "agenda_has_attachments"


def test_meeting_detail_has_enriched_user_refs_with_bounded_queries(
    authenticated_client,
):
    database = authenticated_client.app.state.database
    with database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        reviewer = User(
            username="detail-reviewer",
            display_name="Detail Reviewer",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add(reviewer)
        session.commit()
        admin_id, reviewer_id = admin.id, reviewer.id

    project = authenticated_client.post(
        "/api/projects",
        json={
            "name": "Detailed response",
            "slug": "detailed-response",
            "status": "active",
            "lead_user_id": admin_id,
            "member_ids": [admin_id, reviewer_id],
        },
    ).json()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    meeting = authenticated_client.post(
        f"/api/projects/{project['id']}/meetings",
        json={
            "title": "Detailed meeting",
            "scheduled_start": start.isoformat(),
            "scheduled_end": (start + timedelta(hours=1)).isoformat(),
            "participants": [
                {"user_id": reviewer_id, "participation_role": "attendee"}
            ],
        },
    ).json()
    agenda = authenticated_client.post(
        f"/api/meetings/{meeting['id']}/agenda-items",
        params={"expected_meeting_version": meeting["version"]},
        json={"title": "Contract", "agenda_type": "decision"},
    ).json()
    decision = authenticated_client.post(
        f"/api/projects/{project['id']}/decisions",
        json={
            "meeting_id": meeting["id"],
            "agenda_item_id": agenda["id"],
            "title": "Use refs",
            "decision_markdown": "Use complete user references",
            "reviewer_ids": [reviewer_id],
        },
    ).json()
    authenticated_client.post(
        f"/api/projects/{project['id']}/actions",
        json={
            "project_id": project["id"],
            "meeting_id": meeting["id"],
            "agenda_item_id": agenda["id"],
            "content": "Verify refs",
            "owner_user_id": reviewer_id,
        },
    )
    authenticated_client.post(
        f"/api/projects/{project['id']}/open-questions",
        json={
            "meeting_id": meeting["id"],
            "agenda_item_id": agenda["id"],
            "question_markdown": "Are refs complete?",
            "owner_user_id": reviewer_id,
        },
    )
    with database.session() as session:
        stored_meeting = session.get(Meeting, meeting["id"])
        stored_decision = session.get(Decision, decision["id"])
        stored_decision.decided_by_user_id = reviewer_id
        snapshot = MeetingSnapshot(
            meeting_id=meeting["id"],
            completion_number=1,
            snapshot_json={"schema_version": 1},
            created_by=reviewer_id,
        )
        session.add(snapshot)
        session.flush()
        stored_meeting.current_snapshot = snapshot
        session.add(
            MeetingAmendment(
                meeting_id=meeting["id"],
                reason="Corrected",
                content_markdown="Correction",
                created_by=reviewer_id,
            )
        )
        session.commit()

    statements = []
    with database.session() as session:

        def count_query(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        event.listen(database.engine, "before_cursor_execute", count_query)
        try:
            detail = MeetingService(session).meeting_detail(meeting["id"])
        finally:
            event.remove(database.engine, "before_cursor_execute", count_query)

    reviewer_ref = {
        "id": reviewer_id,
        "username": "detail-reviewer",
        "display_name": "Detail Reviewer",
    }
    admin_ref = detail["created_by"]
    assert detail["snapshots"][0]["created_by"] == reviewer_ref
    assert detail["current_snapshot"]["created_by"] == reviewer_ref
    assert detail["amendments"][0]["created_by"] == reviewer_ref
    agenda_detail = detail["agenda_items"][0]
    assert agenda_detail["decisions"][0]["created_by"] == admin_ref
    assert agenda_detail["decisions"][0]["decided_by"] == reviewer_ref
    assert agenda_detail["decisions"][0]["reviewers"][0]["user"] == reviewer_ref
    assert agenda_detail["actions"][0]["created_by"] == admin_ref
    assert agenda_detail["actions"][0]["owner"] == reviewer_ref
    assert agenda_detail["open_questions"][0]["created_by"] == admin_ref
    assert agenda_detail["open_questions"][0]["owner"] == reviewer_ref
    assert len(statements) <= 10
