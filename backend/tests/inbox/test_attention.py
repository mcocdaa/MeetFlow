from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.auth.models import User, UserRole, UserStatus
from app.collaboration.schemas import CommentWrite
from app.collaboration.service import CommentService
from app.inbox.service import NotificationWriter
from app.outcomes.schemas import ActionWrite, DecisionWrite
from app.outcomes.service import OutcomeService
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService


def test_attention_coalesces_domain_and_unread_reasons_and_tracks_reads(client):
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200

    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        actor = User(
            username="attention-actor",
            display_name="Attention Actor",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add(actor)
        session.commit()
        project = ProjectService(session).create(
            ProjectWrite(
                name="Attention Project",
                slug="attention-project",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id, actor.id],
            ),
            actor,
        )
        writer = NotificationWriter(session)
        for index in range(98):
            writer.add(
                user_id=admin.id,
                actor_user_id=actor.id,
                project_id=project.id,
                meeting_id=None,
                kind="test.bulk",
                subject_type="project",
                subject_id=project.id,
                source_comment_id=None,
                data={"index": index},
                dedupe_key=f"attention-bulk-{index}",
            )
        session.commit()
        outcomes = OutcomeService(session)
        action = outcomes.create_action(
            project.id,
            ActionWrite(
                project_id=project.id,
                content="Repair overdue deployment",
                owner_user_id=admin.id,
                due_date=datetime.now(timezone.utc).date() - timedelta(days=1),
            ),
            actor,
        )
        decision = outcomes.create_decision(
            project.id,
            DecisionWrite(
                title="Approve recovery plan",
                decision_markdown="Use the tested recovery sequence.",
                reviewer_ids=[admin.id],
            ),
            actor,
        )
        comment = CommentService(session).create(
            CommentWrite(
                target_type="project",
                target_id=project.id,
                body_markdown="Please review the deployment context.",
                mention_user_ids=[admin.id],
            ),
            actor,
        )
        NotificationWriter(session).add(
            user_id=actor.id,
            actor_user_id=admin.id,
            project_id=project.id,
            meeting_id=None,
            kind="test.other_user",
            subject_type="project",
            subject_id=project.id,
            source_comment_id=None,
            data={},
            dedupe_key="attention-other-user",
        )
        session.commit()
        action_id = action.id
        decision_id = decision.id
        project_id = project.id
        comment_id = comment.id

    response = client.get("/api/attention")
    assert response.status_code == 200
    body = response.json()
    action_rows = [
        item
        for item in body["items"]
        if item["subject_type"] == "action" and item["subject_id"] == action_id
    ]
    assert len(action_rows) == 1
    assert {"action_overdue", "action_assigned"} <= set(action_rows[0]["reasons"])
    decision_row = next(
        item
        for item in body["items"]
        if item["subject_type"] == "decision" and item["subject_id"] == decision_id
    )
    assert {"decision_review_pending", "decision_review_requested"} <= set(
        decision_row["reasons"]
    )
    assert any(
        item["subject_type"] == "project"
        and item["subject_id"] == project_id
        and "comment_mention" in item["reasons"]
        for item in body["items"]
    )
    assert body["unread_count"] == 101
    assert len(body["notifications"]) == 100
    assert body["truncated"]
    assert {
        "action.assigned",
        "decision.review_requested",
        "comment.mention",
    } <= {item["kind"] for item in body["notifications"]}
    assert {item["id"] for item in body["mentions"]} == {
        item["id"]
        for item in body["notifications"]
        if item["kind"] == "comment.mention"
    }
    assert body["mentions"][0]["source_comment"]["id"] == comment_id

    action_notification_id = next(
        item["id"]
        for item in body["notifications"]
        if item["kind"] == "action.assigned"
    )
    assert client.post(f"/api/inbox/{action_notification_id}/read").status_code == 204
    after_action_read = client.get("/api/attention").json()
    action_row = next(
        item
        for item in after_action_read["items"]
        if item["subject_type"] == "action" and item["subject_id"] == action_id
    )
    assert "action_overdue" in action_row["reasons"]
    assert "action_assigned" not in action_row["reasons"]

    mention_notification_id = next(
        item["id"]
        for item in after_action_read["notifications"]
        if item["kind"] == "comment.mention"
    )
    assert client.post(f"/api/inbox/{mention_notification_id}/read").status_code == 204
    after_mention_read = client.get("/api/attention").json()
    assert not any(
        item["subject_type"] == "project" and item["subject_id"] == project_id
        for item in after_mention_read["items"]
    )
    assert all(
        item["kind"] != "test.other_user"
        for item in after_mention_read["notifications"]
    )

    client.cookies.clear()
    assert client.get("/api/attention").status_code == 401
