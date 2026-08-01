from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agendas.schemas import AgendaWrite
from app.agendas.service import AgendaService
from app.auth.models import User, UserRole, UserStatus
from app.domain.enums import ParticipationRole, ProjectMemberRole
from app.errors import AppError
from app.inbox.models import Notification
from app.meetings.models import Meeting, MeetingParticipant
from app.outcomes.schemas import ActionWrite
from app.outcomes.service import OutcomeService
from app.plugins.context import PluginContextBuilder
from app.plugins.models import PluginJob, PluginJobStatus
from app.projects.models import ProjectMember
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService


@dataclass
class AccessRows:
    admin: User
    lead: User
    member: User
    stakeholder: User
    outsider: User
    invited: User
    inactive_invited: User
    project_id: str
    meeting_id: str


@dataclass
class AccessHttpContext:
    project_id: str
    meeting_id: str
    admin_cookie: dict[str, str]
    lead_cookie: dict[str, str]
    member_cookie: dict[str, str]
    stakeholder_cookie: dict[str, str]
    outsider_cookie: dict[str, str]
    invited_cookie: dict[str, str]


def _active_user(username: str) -> User:
    return User(
        username=username,
        display_name=username.title(),
        password_hash="unused",
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
    )


def _create_http_context(client: TestClient) -> AccessHttpContext:
    database = client.app.state.database
    with database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        lead = _active_user("http-lead")
        member = _active_user("http-member")
        stakeholder = _active_user("http-stakeholder")
        outsider = _active_user("http-outsider")
        invited = _active_user("http-invited")
        session.add_all([lead, member, stakeholder, outsider, invited])
        session.commit()
        project = ProjectService(session).create(
            ProjectWrite(
                name="HTTP access project",
                slug="http-access-project",
                lead_user_id=lead.id,
                member_ids=[lead.id, member.id, stakeholder.id],
            ),
            admin,
        )
        session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == stakeholder.id,
            )
        ).role = ProjectMemberRole.stakeholder
        meeting = Meeting(
            project_id=project.id,
            title="HTTP access meeting",
            scheduled_start=datetime(2026, 8, 1, 9, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
            created_by=lead.id,
            updated_by=lead.id,
            participants=[
                MeetingParticipant(
                    user_id=invited.id,
                    participation_role=ParticipationRole.attendee,
                    position=0,
                )
            ],
        )
        session.add(meeting)
        session.commit()
        cookie_name = client.app.state.auth_service.cookie_name
        issue_cookie = client.app.state.auth_service.issue_cookie
        return AccessHttpContext(
            project_id=project.id,
            meeting_id=meeting.id,
            admin_cookie={cookie_name: issue_cookie(admin)},
            lead_cookie={cookie_name: issue_cookie(lead)},
            member_cookie={cookie_name: issue_cookie(member)},
            stakeholder_cookie={cookie_name: issue_cookie(stakeholder)},
            outsider_cookie={cookie_name: issue_cookie(outsider)},
            invited_cookie={cookie_name: issue_cookie(invited)},
        )


def _as_user(client: TestClient, cookie: dict[str, str]) -> TestClient:
    client.cookies.clear()
    for name, value in cookie.items():
        client.cookies.set(name, value)
    return client


def test_workspace_access_distinguishes_roles(client):
    from app.projects.access import WorkspaceAccess

    database = client.app.state.database
    with database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        lead, member, stakeholder, outsider, invited, inactive_invited = (
            _active_user("access-lead"),
            _active_user("access-member"),
            _active_user("access-stakeholder"),
            _active_user("access-outsider"),
            _active_user("access-invited"),
            _active_user("access-inactive-invited"),
        )
        inactive_invited.status = UserStatus.DISABLED
        session.add_all(
            [lead, member, stakeholder, outsider, invited, inactive_invited]
        )
        session.commit()

        project = ProjectService(session).create(
            ProjectWrite(
                name="Access project",
                slug="access-project",
                lead_user_id=lead.id,
                member_ids=[lead.id, member.id, stakeholder.id],
            ),
            admin,
        )
        session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == stakeholder.id,
            )
        ).role = ProjectMemberRole.stakeholder
        meeting = Meeting(
            project_id=project.id,
            title="Access meeting",
            scheduled_start=datetime(2026, 8, 1, 9, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
            created_by=lead.id,
            updated_by=lead.id,
            participants=[
                MeetingParticipant(
                    user_id=invited.id,
                    participation_role=ParticipationRole.attendee,
                    position=0,
                ),
                MeetingParticipant(
                    user_id=inactive_invited.id,
                    participation_role=ParticipationRole.attendee,
                    position=1,
                ),
            ],
        )
        session.add(meeting)
        session.commit()

        rows = AccessRows(
            admin=admin,
            lead=lead,
            member=member,
            stakeholder=stakeholder,
            outsider=outsider,
            invited=invited,
            inactive_invited=inactive_invited,
            project_id=project.id,
            meeting_id=meeting.id,
        )
        access = WorkspaceAccess(session)
        loaded_project = access.require_project_view(rows.project_id, rows.lead)
        loaded_meeting = access.require_meeting_view(rows.meeting_id, rows.invited)

        assert access.project_capabilities(loaded_project, rows.admin).can_manage
        assert access.project_capabilities(loaded_project, rows.lead).can_manage
        assert access.project_capabilities(loaded_project, rows.member).can_contribute
        assert not access.project_capabilities(loaded_project, rows.member).can_manage
        assert access.project_capabilities(loaded_project, rows.stakeholder).can_view
        assert not access.project_capabilities(
            loaded_project, rows.stakeholder
        ).can_contribute
        assert not access.project_capabilities(loaded_project, rows.outsider).can_view
        assert access.meeting_capabilities(loaded_meeting, rows.invited).can_view
        assert access.meeting_capabilities(loaded_meeting, rows.invited).can_comment
        assert not access.meeting_capabilities(
            loaded_meeting, rows.invited
        ).can_contribute
        assert not any(
            vars(
                access.meeting_capabilities(
                    loaded_meeting, rows.inactive_invited
                )
            ).values()
        )


def test_project_routes_filter_visibility_and_require_management(client):
    context = _create_http_context(client)

    outsider_list = _as_user(client, context.outsider_cookie).get("/api/projects")
    outsider_detail = _as_user(client, context.outsider_cookie).get(
        f"/api/projects/{context.project_id}"
    )
    member_update = _as_user(client, context.member_cookie).put(
        f"/api/projects/{context.project_id}",
        json={"expected_version": 1, "summary": "Member cannot manage"},
    )
    lead_update = _as_user(client, context.lead_cookie).put(
        f"/api/projects/{context.project_id}",
        json={"expected_version": 1, "summary": "Lead can manage"},
    )

    assert outsider_list.status_code == 200
    assert outsider_list.json() == []
    assert outsider_detail.status_code == 403
    assert outsider_detail.json()["error"]["code"] == "project_view_forbidden"
    assert member_update.status_code == 403
    assert member_update.json()["error"]["code"] == "project_management_forbidden"
    assert lead_update.status_code == 200


def test_meeting_routes_allow_invited_view_but_filter_outsiders(client):
    context = _create_http_context(client)

    invited_detail = _as_user(client, context.invited_cookie).get(
        f"/api/meetings/{context.meeting_id}"
    )
    invited_update = _as_user(client, context.invited_cookie).put(
        f"/api/meetings/{context.meeting_id}",
        json={"expected_version": 1, "title": "Invited cannot update"},
    )
    outsider_detail = _as_user(client, context.outsider_cookie).get(
        f"/api/meetings/{context.meeting_id}"
    )
    outsider_global = _as_user(client, context.outsider_cookie).get(
        "/api/meetings"
    )

    assert invited_detail.status_code == 200
    assert invited_update.status_code == 403
    assert outsider_detail.status_code == 403
    assert outsider_global.status_code == 200
    assert outsider_global.json()["items"] == []


def test_nonmember_cannot_comment_on_or_upload_to_a_meeting(client):
    context = _create_http_context(client)

    comment = _as_user(client, context.outsider_cookie).post(
        "/api/comments",
        json={
            "target_type": "meeting",
            "target_id": context.meeting_id,
            "body_markdown": "Outsider comment",
            "mention_user_ids": [],
        },
    )

    assert comment.status_code == 403
    assert comment.json()["error"]["code"] == "meeting_comment_forbidden"

    upload = _as_user(client, context.outsider_cookie).post(
        f"/api/attachments/meeting/{context.meeting_id}",
        files={"file": ("outsider.txt", b"no access", "text/plain")},
    )

    assert upload.status_code == 403
    assert upload.json()["error"]["code"] == "project_contribution_forbidden"


def test_invited_nonmember_can_comment_but_cannot_upload_to_own_meeting(client):
    context = _create_http_context(client)

    comment = _as_user(client, context.invited_cookie).post(
        "/api/comments",
        json={
            "target_type": "meeting",
            "target_id": context.meeting_id,
            "body_markdown": "Invited attendee comment",
            "mention_user_ids": [],
        },
    )
    listed = _as_user(client, context.invited_cookie).get(
        "/api/comments",
        params={"target_type": "meeting", "target_id": context.meeting_id},
    )
    upload = _as_user(client, context.invited_cookie).post(
        f"/api/attachments/meeting/{context.meeting_id}",
        files={"file": ("invited.txt", b"no upload access", "text/plain")},
    )

    assert comment.status_code == 201
    assert {
        key: comment.json()[key]
        for key in ("can_edit", "can_delete", "can_resolve")
    } == {"can_edit": True, "can_delete": True, "can_resolve": True}
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [comment.json()["id"]]
    assert upload.status_code == 403
    assert upload.json()["error"]["code"] == "project_contribution_forbidden"


def test_nonmember_cannot_create_agendas_or_project_outcomes(client):
    context = _create_http_context(client)

    agenda = _as_user(client, context.outsider_cookie).post(
        f"/api/meetings/{context.meeting_id}/agenda-items",
        params={"expected_meeting_version": 1},
        json={"title": "Outsider agenda", "agenda_type": "discussion"},
    )

    assert agenda.status_code == 403
    assert agenda.json()["error"]["code"] == "project_view_forbidden"

    decision = _as_user(client, context.outsider_cookie).post(
        f"/api/projects/{context.project_id}/decisions",
        json={
            "title": "Outsider decision",
            "decision_markdown": "No authority",
            "rationale_markdown": "",
            "reviewer_ids": [],
        },
    )

    assert decision.status_code == 403
    assert decision.json()["error"]["code"] == "project_contribution_forbidden"


def test_agenda_service_requires_project_contribution(client):
    context = _create_http_context(client)
    database = client.app.state.database

    with database.session() as session:
        outsider = session.scalar(
            select(User).where(User.username == "http-outsider")
        )
        assert outsider is not None

        with pytest.raises(AppError) as error:
            AgendaService(session).create(
                context.meeting_id,
                AgendaWrite(title="Service bypass", agenda_type="discussion"),
                outsider,
                expected_meeting_version=1,
            )

    assert error.value.code == "project_view_forbidden"


def test_stakeholder_can_list_but_cannot_create_project_outcomes(client):
    context = _create_http_context(client)

    listed = _as_user(client, context.stakeholder_cookie).get(
        f"/api/projects/{context.project_id}/decisions"
    )
    decision = _as_user(client, context.stakeholder_cookie).post(
        f"/api/projects/{context.project_id}/decisions",
        json={
            "title": "Stakeholder decision",
            "decision_markdown": "No write authority",
            "rationale_markdown": "",
            "reviewer_ids": [],
        },
    )

    assert listed.status_code == 200
    assert listed.json() == []
    assert decision.status_code == 403
    assert decision.json()["error"]["code"] == "project_contribution_forbidden"


def test_project_activity_respects_workspace_visibility(client):
    context = _create_http_context(client)

    outsider = _as_user(client, context.outsider_cookie).get(
        f"/api/projects/{context.project_id}/activity"
    )
    stakeholder = _as_user(client, context.stakeholder_cookie).get(
        f"/api/projects/{context.project_id}/activity"
    )

    assert outsider.status_code == 403
    assert outsider.json()["error"]["code"] == "project_view_forbidden"
    assert stakeholder.status_code == 200


def test_attention_and_work_brief_omit_private_assigned_actions(client):
    context = _create_http_context(client)
    database = client.app.state.database

    with database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        outsider = session.scalar(
            select(User).where(User.username == "http-outsider")
        )
        assert admin is not None and outsider is not None
        OutcomeService(session).create_action(
            context.project_id,
            ActionWrite(
                project_id=context.project_id,
                content="Private deployment action",
                owner_user_id=outsider.id,
                due_date=date.today() + timedelta(days=1),
            ),
            admin,
        )

    attention = _as_user(client, context.outsider_cookie).get("/api/attention")

    assert attention.status_code == 200
    assert attention.json()["items"] == []
    assert attention.json()["notifications"] == []
    assert attention.json()["unread_count"] == 0

    with database.session() as session:
        outsider = session.scalar(
            select(User).where(User.username == "http-outsider")
        )
        assert outsider is not None
        brief = PluginContextBuilder(session).user_work_brief(outsider)

    assert brief["projects"] == []
    assert brief["attention"]["items"] == []
    assert brief["attention"]["notifications"] == []


def test_inbox_omits_notifications_outside_workspace_access(client):
    context = _create_http_context(client)
    database = client.app.state.database

    with database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        outsider = session.scalar(
            select(User).where(User.username == "http-outsider")
        )
        assert admin is not None and outsider is not None
        action = OutcomeService(session).create_action(
            context.project_id,
            ActionWrite(
                project_id=context.project_id,
                content="Private inbox action",
                owner_user_id=outsider.id,
            ),
            admin,
        )
        notification = session.scalar(
            select(Notification).where(
                Notification.user_id == outsider.id,
                Notification.subject_id == action.id,
            )
        )
        assert notification is not None
        notification_id = notification.id

    history = _as_user(client, context.outsider_cookie).get("/api/inbox")
    changes = _as_user(client, context.outsider_cookie).get("/api/inbox/changes")
    read = _as_user(client, context.outsider_cookie).post(
        f"/api/inbox/{notification_id}/read"
    )
    read_all = _as_user(client, context.outsider_cookie).post("/api/inbox/read-all")

    assert history.status_code == 200
    assert history.json()["items"] == []
    assert history.json()["unread_count"] == 0
    assert changes.status_code == 200
    assert changes.json()["notifications"] == []
    assert changes.json()["unread_count"] == 0
    assert read.status_code == 404
    assert read.json()["error"]["code"] == "notification_not_found"
    assert read_all.status_code == 204

    with database.session() as session:
        notification = session.get(Notification, notification_id)
        assert notification is not None
        assert notification.read_at is None


def test_invited_participant_receives_meeting_action_comment_notifications(client):
    context = _create_http_context(client)
    database = client.app.state.database

    with database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        invited = session.scalar(select(User).where(User.username == "http-invited"))
        assert admin is not None and invited is not None
        action = OutcomeService(session).create_action(
            context.project_id,
            ActionWrite(
                project_id=context.project_id,
                meeting_id=context.meeting_id,
                content="Meeting action open for comment",
            ),
            admin,
        )
        invited_id = invited.id

    mentioned = _as_user(client, context.admin_cookie).post(
        "/api/comments",
        json={
            "target_type": "action_item",
            "target_id": action.id,
            "body_markdown": "Please review this meeting action",
            "mention_user_ids": [invited_id],
        },
    )
    inbox = _as_user(client, context.invited_cookie).get("/api/inbox")
    attention = _as_user(client, context.invited_cookie).get("/api/attention")

    assert mentioned.status_code == 201
    assert inbox.status_code == 200
    assert [item["subject"] for item in inbox.json()["items"]] == [
        {"type": "action_item", "id": action.id}
    ]
    assert attention.status_code == 200
    assert [item["subject"] for item in attention.json()["notifications"]] == [
        {"type": "action_item", "id": action.id}
    ]
    assert [item["subject_id"] for item in attention.json()["items"]] == [action.id]


def test_attachment_payload_only_allows_author_or_admin_to_delete(client):
    context = _create_http_context(client)

    uploaded = _as_user(client, context.lead_cookie).post(
        f"/api/attachments/meeting/{context.meeting_id}",
        files={"file": ("shared.txt", b"shared", "text/plain")},
    )
    listed = _as_user(client, context.member_cookie).get(
        f"/api/attachments/meeting/{context.meeting_id}"
    )
    detail = _as_user(client, context.member_cookie).get(
        f"/api/meetings/{context.meeting_id}"
    )

    assert uploaded.status_code == 201
    assert uploaded.json()["can_delete"] is True
    assert listed.status_code == 200
    assert listed.json()[0]["can_delete"] is False
    assert detail.status_code == 200
    assert detail.json()["attachments"][0]["can_delete"] is False


def test_plugin_jobs_stop_exposing_results_after_membership_revocation(client):
    context = _create_http_context(client)
    database = client.app.state.database

    with database.session() as session:
        member = session.scalar(select(User).where(User.username == "http-member"))
        assert member is not None
        membership = session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == context.project_id,
                ProjectMember.user_id == member.id,
            )
        )
        assert membership is not None
        session.delete(membership)
        job = PluginJob(
            plugin_id="test-ai",
            action_id="test-ai.summarize",
            target_type="meeting",
            target_id=context.meeting_id,
            dedupe_key=f"revoked:meeting:{context.meeting_id}",
            status=PluginJobStatus.succeeded,
            input_json={},
            context_snapshot={},
            result_json={"markdown": "private meeting result"},
            created_by=member.id,
        )
        session.add(job)
        session.commit()
        job_id = job.id

    detail = _as_user(client, context.member_cookie).get(
        f"/api/plugin-jobs/{job_id}"
    )
    listed = _as_user(client, context.member_cookie).get("/api/plugin-jobs")

    assert detail.status_code == 403
    assert detail.json()["error"]["code"] == "project_view_forbidden"
    assert listed.status_code == 200
    assert listed.json()["items"] == []


def test_plugin_job_list_ignores_deleted_targets(client):
    context = _create_http_context(client)
    database = client.app.state.database

    with database.session() as session:
        member = session.scalar(select(User).where(User.username == "http-member"))
        assert member is not None
        session.add(
            PluginJob(
                plugin_id="test-ai",
                action_id="test-ai.summarize",
                target_type="meeting",
                target_id="missing-meeting",
                dedupe_key="deleted:meeting:missing-meeting",
                status=PluginJobStatus.succeeded,
                input_json={},
                context_snapshot={},
                result_json={"markdown": "expired result"},
                created_by=member.id,
            )
        )
        session.commit()

    listed = _as_user(client, context.member_cookie).get("/api/plugin-jobs")

    assert listed.status_code == 200
    assert listed.json()["items"] == []
