from itertools import count

import pytest
from sqlalchemy import select

from app.auth.models import User, UserRole, UserStatus
from app.collaboration.schemas import CommentEdit, CommentWrite
from app.collaboration.service import CommentService
from app.errors import AppError
from app.inbox.models import Notification
from app.inbox.service import NotificationWriter
from app.outcomes.models import ActionItem
from app.outcomes.schemas import ActionEdit, ActionWrite, DecisionEdit, DecisionWrite
from app.outcomes.service import OutcomeService
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService

_unique = count()


@pytest.fixture
def notification_context(client):
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        users = [
            User(
                username=f"notify-{label}-{next(_unique)}",
                display_name=f"Notify {label}",
                password_hash="unused",
                role=UserRole.MEMBER,
                status=UserStatus.ACTIVE,
            )
            for label in ("member", "other", "third")
        ]
        session.add_all(users)
        session.commit()
        project = ProjectService(session).create(
            ProjectWrite(
                name="Notification project",
                slug=f"notification-project-{next(_unique)}",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id, *(user.id for user in users)],
            ),
            admin,
        )
        return {
            "admin_id": admin.id,
            "user_ids": [user.id for user in users],
            "project_id": project.id,
        }


def _auth_headers(client, user_id: str) -> dict[str, str]:
    with client.app.state.database.session() as session:
        user = session.get(User, user_id)
        service = client.app.state.auth_service
        return {"cookie": f"{service.cookie_name}={service.issue_cookie(user)}"}


def _add_notification(
    session, *, user_id: str, actor_id: str, project_id: str, key: str
):
    return NotificationWriter(session).add(
        user_id=user_id,
        actor_user_id=actor_id,
        project_id=project_id,
        meeting_id=None,
        kind="test.notification",
        subject_type="project",
        subject_id=project_id,
        source_comment_id=None,
        data={"sequence": key},
        dedupe_key=key,
    )


def test_domain_notifications_reach_only_new_direct_recipients_and_dedupe(
    client, notification_context
):
    context = notification_context
    member_id, other_id, third_id = context["user_ids"]
    with client.app.state.database.session() as session:
        admin = session.get(User, context["admin_id"])
        member = session.get(User, member_id)
        other = session.get(User, other_id)
        comments = CommentService(session)
        root = comments.create(
            CommentWrite(
                target_type="project",
                target_id=context["project_id"],
                body_markdown="Member root",
            ),
            member,
        )
        reply = comments.create(
            CommentWrite(
                target_type="project",
                target_id=context["project_id"],
                parent_id=root.id,
                body_markdown="Admin reply",
            ),
            admin,
        )
        nested_reply = comments.create(
            CommentWrite(
                target_type="project",
                target_id=context["project_id"],
                parent_id=reply.id,
                body_markdown="Other replies directly to admin",
            ),
            other,
        )
        assert nested_reply.parent_id == root.id
        mentioned = comments.create(
            CommentWrite(
                target_type="project",
                target_id=context["project_id"],
                body_markdown="Mention body must stay private",
                mention_user_ids=[member_id, admin.id, member_id],
            ),
            admin,
        )
        mentioned = comments.update(
            mentioned.id,
            CommentEdit(
                expected_version=mentioned.version,
                body_markdown="Edited private body",
                mention_user_ids=[member_id, other_id],
            ),
            admin,
        )

        outcomes = OutcomeService(session)
        action = outcomes.create_action(
            context["project_id"],
            ActionWrite(
                project_id=context["project_id"],
                content="Assigned action",
                owner_user_id=member_id,
            ),
            admin,
        )
        action = outcomes.update_action(
            action.id,
            ActionEdit(expected_version=action.version, owner_user_id=other_id),
            admin,
        )
        action_id = action.id
        self_action = outcomes.create_action(
            context["project_id"],
            ActionWrite(
                project_id=context["project_id"],
                content="Self action",
                owner_user_id=admin.id,
            ),
            admin,
        )
        decision = outcomes.create_decision(
            context["project_id"],
            DecisionWrite(
                title="Review decision",
                decision_markdown="Private decision markdown",
                reviewer_ids=[member_id, admin.id],
            ),
            admin,
        )
        decision = outcomes.update_decision(
            decision.id,
            DecisionEdit(
                expected_version=decision.version,
                reviewer_ids=[member_id, other_id],
            ),
            admin,
        )
        self_decision = outcomes.create_decision(
            context["project_id"],
            DecisionWrite(
                title="Self review",
                decision_markdown="No notification",
                reviewer_ids=[admin.id],
            ),
            admin,
        )

        notifications = list(session.scalars(select(Notification)))
        mention_rows = [
            item for item in notifications if item.source_comment_id == mentioned.id
        ]
        assert {(item.kind, item.user_id) for item in mention_rows} == {
            ("comment.mention", member_id),
            ("comment.mention", other_id),
        }
        assert all("body" not in str(item.data_json).lower() for item in mention_rows)
        assert {
            item.user_id
            for item in notifications
            if item.kind == "comment.reply" and item.source_comment_id == reply.id
        } == {member_id}
        nested_reply_rows = [
            item
            for item in notifications
            if item.kind == "comment.reply"
            and item.source_comment_id == nested_reply.id
        ]
        assert {item.user_id for item in nested_reply_rows} == {context["admin_id"]}
        assert {
            item.data_json["replied_to_comment_id"] for item in nested_reply_rows
        } == {reply.id}
        assert {
            item.user_id
            for item in notifications
            if item.kind == "action.assigned" and item.subject_id == action.id
        } == {member_id, other_id}
        assert not any(item.subject_id == self_action.id for item in notifications)
        assert {
            item.user_id
            for item in notifications
            if item.kind == "decision.review_requested"
            and item.subject_id == decision.id
        } == {member_id, other_id}
        assert not any(item.subject_id == self_decision.id for item in notifications)
        assert len({item.dedupe_key for item in notifications}) == len(notifications)

        writer = NotificationWriter(session)
        first = writer.add(
            user_id=third_id,
            actor_user_id=admin.id,
            project_id=context["project_id"],
            meeting_id=None,
            kind="test.notification",
            subject_type="project",
            subject_id=context["project_id"],
            source_comment_id=None,
            data={"version": 1},
            dedupe_key="same-transaction-dedupe",
        )
        second = writer.add(
            user_id=third_id,
            actor_user_id=admin.id,
            project_id=context["project_id"],
            meeting_id=None,
            kind="test.notification",
            subject_type="project",
            subject_id=context["project_id"],
            source_comment_id=None,
            data={"version": 1},
            dedupe_key="same-transaction-dedupe",
        )
        assert first is second
        session.commit()
        existing = writer.add(
            user_id=third_id,
            actor_user_id=admin.id,
            project_id=context["project_id"],
            meeting_id=None,
            kind="test.notification",
            subject_type="project",
            subject_id=context["project_id"],
            source_comment_id=None,
            data={"version": 1},
            dedupe_key="same-transaction-dedupe",
        )
        assert existing.id == first.id
        session.commit()
        assert (
            len(
                list(
                    session.scalars(
                        select(Notification).where(
                            Notification.user_id == third_id,
                            Notification.dedupe_key == "same-transaction-dedupe",
                        )
                    )
                )
            )
            == 1
        )

    database = client.app.state.database
    with database.session() as stale, database.session() as winner:
        stale_actor = stale.get(User, context["admin_id"])
        winner_actor = winner.get(User, context["admin_id"])
        stale_action = stale.get(ActionItem, action_id)
        expected_version = stale_action.version

        winner_action = OutcomeService(winner).update_action(
            action_id,
            ActionEdit(
                expected_version=expected_version,
                content="Winner action content",
            ),
            winner_actor,
        )
        assert winner_action.version == expected_version + 1

        with pytest.raises(AppError) as conflict:
            OutcomeService(stale).update_action(
                action_id,
                ActionEdit(
                    expected_version=expected_version,
                    owner_user_id=third_id,
                ),
                stale_actor,
            )
        assert conflict.value.status_code == 409
        assert conflict.value.code == "version_conflict"

    with database.session() as independent:
        persisted = independent.get(ActionItem, action_id)
        assert persisted.content == "Winner action content"
        assert persisted.version == expected_version + 1
        assert (
            independent.scalar(
                select(Notification.id).where(
                    Notification.kind == "action.assigned",
                    Notification.subject_id == action_id,
                    Notification.user_id == third_id,
                )
            )
            is None
        )


def test_inbox_changes_and_history_are_user_scoped_gap_free_and_authenticated(
    client, notification_context
):
    context = notification_context
    first_user, second_user, _ = context["user_ids"]
    with client.app.state.database.session() as session:
        for index in range(5):
            _add_notification(
                session,
                user_id=first_user,
                actor_id=context["admin_id"],
                project_id=context["project_id"],
                key=f"first-{index}",
            )
        for index in range(2):
            _add_notification(
                session,
                user_id=second_user,
                actor_id=context["admin_id"],
                project_id=context["project_id"],
                key=f"second-{index}",
            )
        session.commit()

    first_headers = _auth_headers(client, first_user)
    first_page = client.get(
        "/api/inbox/changes",
        params={"cursor": 0, "limit": 2},
        headers=first_headers,
    ).json()
    second_page = client.get(
        "/api/inbox/changes",
        params={"cursor": first_page["next_cursor"], "limit": 2},
        headers=first_headers,
    ).json()
    third_page = client.get(
        "/api/inbox/changes",
        params={"cursor": second_page["next_cursor"], "limit": 2},
        headers=first_headers,
    ).json()
    ids = [
        item["id"]
        for page in (first_page, second_page, third_page)
        for item in page["notifications"]
    ]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids)) == 5
    assert first_page["has_more"] and second_page["has_more"]
    assert not third_page["has_more"]
    assert third_page["next_cursor"] == ids[-1]

    history_first = client.get(
        "/api/inbox", params={"limit": 2}, headers=first_headers
    ).json()
    history_second = client.get(
        "/api/inbox",
        params={"before": history_first["next_cursor"], "limit": 2},
        headers=first_headers,
    ).json()
    history_ids = [
        item["id"] for item in history_first["items"] + history_second["items"]
    ]
    assert history_ids == sorted(history_ids, reverse=True)
    assert len(history_ids) == len(set(history_ids)) == 4

    second_changes = client.get(
        "/api/inbox/changes",
        params={"cursor": 0},
        headers=_auth_headers(client, second_user),
    ).json()
    assert {item["id"] for item in second_changes["notifications"]}.isdisjoint(ids)
    assert client.get("/api/inbox/changes").status_code == 401


def test_inbox_read_commands_are_owned_idempotent_and_preserve_other_users(
    client, notification_context
):
    context = notification_context
    first_user, second_user, _ = context["user_ids"]
    with client.app.state.database.session() as session:
        first_rows = [
            _add_notification(
                session,
                user_id=first_user,
                actor_id=context["admin_id"],
                project_id=context["project_id"],
                key=f"read-first-{index}",
            )
            for index in range(3)
        ]
        second_row = _add_notification(
            session,
            user_id=second_user,
            actor_id=context["admin_id"],
            project_id=context["project_id"],
            key="read-second",
        )
        session.commit()
        first_id = first_rows[0].id
        second_id = second_row.id

    first_headers = _auth_headers(client, first_user)
    second_headers = _auth_headers(client, second_user)
    assert client.get("/api/inbox", headers=first_headers).json()["unread_count"] == 3
    forbidden = client.post(f"/api/inbox/{second_id}/read", headers=first_headers)
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "notification_not_found"
    assert (
        client.post(f"/api/inbox/{first_id}/read", headers=first_headers).status_code
        == 204
    )
    assert (
        client.post(f"/api/inbox/{first_id}/read", headers=first_headers).status_code
        == 204
    )
    assert client.get("/api/inbox", headers=first_headers).json()["unread_count"] == 2
    assert client.post("/api/inbox/read-all", headers=first_headers).status_code == 204
    assert client.post("/api/inbox/read-all", headers=first_headers).status_code == 204
    assert client.get("/api/inbox", headers=first_headers).json()["unread_count"] == 0
    assert client.get("/api/inbox", headers=second_headers).json()["unread_count"] == 1
