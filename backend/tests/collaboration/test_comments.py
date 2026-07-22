from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agendas.schemas import AgendaCommand, AgendaWrite
from app.agendas.service import AgendaService
from app.auth.models import User, UserRole, UserStatus
from app.collaboration.models import ActivityEvent, Comment
from app.collaboration.schemas import CommentCommand, CommentEdit, CommentWrite
from app.collaboration.service import CommentService
from app.errors import AppError
from app.meetings.schemas import MeetingWrite
from app.meetings.service import MeetingService
from app.outcomes.schemas import ActionWrite, DecisionWrite
from app.outcomes.service import OutcomeService
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService

START = datetime(2026, 7, 22, 14, tzinfo=timezone.utc)


@pytest.fixture
def comment_context(client):
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        member = User(
            username="comment-member",
            display_name="Comment Member",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        other = User(
            username="comment-other",
            display_name="Comment Other",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        inactive = User(
            username="comment-inactive",
            display_name="Comment Inactive",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.DISABLED,
        )
        session.add_all([member, other, inactive])
        session.commit()
        project = ProjectService(session).create(
            ProjectWrite(
                name="Comment project",
                slug="comment-project",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id, member.id, other.id],
            ),
            admin,
        )
        meeting = MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Comment meeting",
                scheduled_start=START,
                scheduled_end=START + timedelta(hours=1),
            ),
            admin,
        )
        agenda = AgendaService(session).create(
            meeting.id,
            AgendaWrite(title="Comment agenda", agenda_type="discussion"),
            admin,
            expected_meeting_version=meeting.version,
        )
        outcomes = OutcomeService(session)
        decision = outcomes.create_decision(
            project.id,
            DecisionWrite(
                meeting_id=meeting.id,
                title="Comment decision",
                decision_markdown="Decision",
            ),
            admin,
        )
        action = outcomes.create_action(
            project.id,
            ActionWrite(
                project_id=project.id,
                meeting_id=meeting.id,
                content="Comment action",
            ),
            admin,
        )
        return {
            "admin_id": admin.id,
            "member_id": member.id,
            "other_id": other.id,
            "inactive_id": inactive.id,
            "project_id": project.id,
            "meeting_id": meeting.id,
            "agenda_id": agenda.id,
            "decision_id": decision.id,
            "action_id": action.id,
        }


def test_comments_support_five_targets_and_reject_invalid_context(
    client, comment_context
):
    context = comment_context
    targets = {
        "project": context["project_id"],
        "meeting": context["meeting_id"],
        "agenda_item": context["agenda_id"],
        "decision": context["decision_id"],
        "action_item": context["action_id"],
    }
    with client.app.state.database.session() as session:
        actor = session.get(User, context["admin_id"])
        service = CommentService(session)
        created = {
            target_type: service.create(
                CommentWrite(
                    target_type=target_type,
                    target_id=target_id,
                    body_markdown=f"Comment on {target_type}",
                ),
                actor,
            )
            for target_type, target_id in targets.items()
        }
        assert {item.target_type for item in created.values()} == set(targets)
        assert created["project"].meeting_id is None
        assert all(
            item.project_id == context["project_id"] for item in created.values()
        )
        assert all(
            created[name].meeting_id == context["meeting_id"]
            for name in ("meeting", "agenda_item", "decision", "action_item")
        )

        with pytest.raises(AppError) as missing:
            service.create(
                CommentWrite(
                    target_type="meeting",
                    target_id="missing",
                    body_markdown="Missing",
                ),
                actor,
            )
        assert (missing.value.status_code, missing.value.code) == (
            404,
            "comment_target_not_found",
        )

        with pytest.raises(AppError) as unsupported:
            service.create(
                CommentWrite(
                    target_type="open_question",
                    target_id=context["project_id"],
                    body_markdown="Unsupported",
                ),
                actor,
            )
        assert (unsupported.value.status_code, unsupported.value.code) == (
            422,
            "unsupported_comment_target",
        )

        with pytest.raises(AppError) as mismatch:
            service.create(
                CommentWrite(
                    target_type="meeting",
                    target_id=context["meeting_id"],
                    parent_id=created["project"].id,
                    body_markdown="Wrong thread",
                ),
                actor,
            )
        assert mismatch.value.code == "comment_parent_mismatch"


def test_reply_flatten_edit_permissions_and_delete_tombstone_keep_context(
    client, comment_context
):
    context = comment_context
    with client.app.state.database.session() as session:
        admin = session.get(User, context["admin_id"])
        member = session.get(User, context["member_id"])
        other = session.get(User, context["other_id"])
        service = CommentService(session)
        root = service.create(
            CommentWrite(
                target_type="meeting",
                target_id=context["meeting_id"],
                body_markdown="Root",
            ),
            admin,
        )
        reply = service.create(
            CommentWrite(
                target_type="meeting",
                target_id=context["meeting_id"],
                parent_id=root.id,
                body_markdown="Reply",
            ),
            member,
        )
        nested = service.create(
            CommentWrite(
                target_type="meeting",
                target_id=context["meeting_id"],
                parent_id=reply.id,
                body_markdown="Flattened",
            ),
            other,
        )
        assert reply.parent_id == root.id
        assert nested.parent_id == root.id

        with pytest.raises(AppError) as forbidden:
            service.update(
                root.id,
                CommentEdit(expected_version=root.version, body_markdown="Hijack"),
                other,
            )
        assert forbidden.value.code == "comment_edit_forbidden"

        edited = service.update(
            reply.id,
            CommentEdit(expected_version=reply.version, body_markdown="Edited reply"),
            admin,
        )
        assert edited.edited_at is not None
        deleted = service.delete(
            root.id, CommentCommand(expected_version=root.version), admin
        )
        assert deleted.body_markdown is None
        assert deleted.deleted_at is not None
        deleted_event_count = len(
            list(
                session.scalars(
                    select(ActivityEvent).where(
                        ActivityEvent.event_type == "comment.deleted",
                        ActivityEvent.subject_id == root.id,
                    )
                )
            )
        )
        same = service.delete(
            root.id, CommentCommand(expected_version=deleted.version), admin
        )
        assert same.version == deleted.version
        assert (
            len(
                list(
                    session.scalars(
                        select(ActivityEvent).where(
                            ActivityEvent.event_type == "comment.deleted",
                            ActivityEvent.subject_id == root.id,
                        )
                    )
                )
            )
            == deleted_event_count
        )
        thread = service.list_for_target("meeting", context["meeting_id"])
        assert len(thread) == 1
        assert thread[0].body_markdown is None
        assert [item.body_markdown for item in thread[0].replies] == [
            "Edited reply",
            "Flattened",
        ]


def test_mentions_are_explicit_active_atomic_and_activity_omits_body(
    client, comment_context
):
    context = comment_context
    secret = "PRIVATE COMMENT BODY"
    with client.app.state.database.session() as session:
        actor = session.get(User, context["admin_id"])
        service = CommentService(session)
        comment = service.create(
            CommentWrite(
                target_type="project",
                target_id=context["project_id"],
                body_markdown=secret,
                mention_user_ids=[
                    context["member_id"],
                    actor.id,
                    context["member_id"],
                ],
            ),
            actor,
        )
        assert [mention.user_id for mention in comment.mentions] == [
            context["member_id"]
        ]

        before_ids = set(session.scalars(select(Comment.id)))
        with pytest.raises(AppError) as invalid:
            service.create(
                CommentWrite(
                    target_type="project",
                    target_id=context["project_id"],
                    body_markdown="Must roll back",
                    mention_user_ids=[context["inactive_id"], "missing-user"],
                ),
                actor,
            )
        assert invalid.value.code == "comment_mention_user_invalid"
        assert set(session.scalars(select(Comment.id))) == before_ids

        event = session.scalar(
            select(ActivityEvent).where(
                ActivityEvent.event_type == "comment.created",
                ActivityEvent.subject_id == comment.id,
            )
        )
        assert event.payload_json == {
            "target_type": "project",
            "target_id": context["project_id"],
            "parent_id": None,
        }
        assert secret not in str(event.payload_json)


def test_comment_api_auth_versions_and_agenda_delete_guard(
    client, authenticated_client, comment_context
):
    context = comment_context
    authenticated_client.post("/api/auth/logout")
    assert (
        client.get(
            "/api/comments",
            params={"target_type": "agenda_item", "target_id": context["agenda_id"]},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/comments",
            json={
                "target_type": "agenda_item",
                "target_id": context["agenda_id"],
                "body_markdown": "No auth",
            },
        ).status_code
        == 401
    )
    assert (
        authenticated_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct-horse-battery"},
        ).status_code
        == 200
    )
    created = authenticated_client.post(
        "/api/comments",
        json={
            "target_type": "agenda_item",
            "target_id": context["agenda_id"],
            "body_markdown": "Guard this agenda",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["can_edit"] and body["can_delete"]
    conflict = authenticated_client.put(
        f"/api/comments/{body['id']}",
        json={"expected_version": body["version"] + 1, "body_markdown": "Stale"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "version_conflict"

    deleted = authenticated_client.request(
        "DELETE",
        f"/api/comments/{body['id']}",
        json={"expected_version": body["version"]},
    )
    assert deleted.status_code == 204
    thread = authenticated_client.get(
        "/api/comments",
        params={"target_type": "agenda_item", "target_id": context["agenda_id"]},
    ).json()["items"]
    assert thread[0]["body_markdown"] is None

    meeting = authenticated_client.get(f"/api/meetings/{context['meeting_id']}").json()
    with client.app.state.database.session() as session:
        agenda = session.get(Comment, body["id"])
        assert agenda.deleted_at is not None
        item_version = session.execute(
            select(Comment.target_id).where(Comment.id == body["id"])
        ).scalar_one()
        assert item_version == context["agenda_id"]
    with client.app.state.database.session() as session:
        agenda_service = AgendaService(session)
        actor = session.get(User, context["admin_id"])
        agenda_item = agenda_service.get(context["agenda_id"])
        with pytest.raises(AppError) as guarded:
            agenda_service.delete(
                agenda_item.id,
                AgendaCommand(expected_version=agenda_item.version),
                actor,
                expected_meeting_version=meeting["version"],
            )
        assert guarded.value.code == "agenda_has_comments"
