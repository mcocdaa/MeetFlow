from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.agendas.models import AgendaItem
from app.agendas.schemas import AgendaCommand, AgendaWrite
from app.agendas.service import AgendaService
from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.meetings.models import Meeting
from app.meetings.schemas import MeetingWrite
from app.meetings.service import MeetingService
from app.outcomes.models import ActionItem, Decision, OpenQuestion
from app.outcomes.schemas import (
    ActionEdit,
    ActionWrite,
    AgendaCopyWrite,
    AgendaConvertWrite,
    AgendaOutcomeMigrationWrite,
    DecisionFinalizeWrite,
    DecisionReviewWrite,
    DecisionSupersedeWrite,
    DecisionWrite,
    QuestionResolveWrite,
    QuestionScheduleWrite,
    QuestionWrite,
)
from app.outcomes.service import OutcomeService
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService

START = datetime(2026, 8, 3, 9, tzinfo=timezone.utc)


@pytest.fixture
def outcome_context(client):
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        reviewer = User(
            username="outcome-reviewer",
            display_name="Reviewer",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        outsider = User(
            username="outcome-outsider",
            display_name="Outsider",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add_all([reviewer, outsider])
        session.commit()
        project = ProjectService(session).create(
            ProjectWrite(
                name="Outcome domain",
                slug="outcome-domain",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id, reviewer.id, outsider.id],
            ),
            admin,
        )
        service = MeetingService(session)
        meeting = service.create_meeting(
            project.id,
            MeetingWrite(
                title="Current meeting",
                scheduled_start=START,
                scheduled_end=START + timedelta(hours=1),
            ),
            admin,
        )
        future = service.create_meeting(
            project.id,
            MeetingWrite(
                title="Future meeting",
                scheduled_start=START + timedelta(days=7),
                scheduled_end=START + timedelta(days=7, hours=1),
            ),
            admin,
        )
        agenda_service = AgendaService(session)
        agenda = agenda_service.create(
            meeting.id,
            AgendaWrite(title="Source", agenda_type="decision"),
            admin,
            expected_meeting_version=meeting.version,
        )
        session.refresh(meeting)
        target = agenda_service.create(
            meeting.id,
            AgendaWrite(title="Target", agenda_type="discussion"),
            admin,
            expected_meeting_version=meeting.version,
        )
        values = (
            admin.id,
            reviewer.id,
            outsider.id,
            project.id,
            meeting.id,
            future.id,
            agenda.id,
            target.id,
        )
        return values


def test_source_chain_and_reviewer_response_are_traceable(client, outcome_context):
    admin_id, reviewer_id, outsider_id, project_id, meeting_id, _, agenda_id, _ = (
        outcome_context
    )
    with client.app.state.database.session() as session:
        service = OutcomeService(session)
        actor = session.get(User, admin_id)
        reviewer = session.get(User, reviewer_id)
        decision = service.create_decision(
            project_id,
            DecisionWrite(
                meeting_id=meeting_id,
                agenda_item_id=agenda_id,
                title="  Use capability declarations  ",
                decision_markdown="  **Preserve** this markdown.\n",
                reviewer_ids=[reviewer_id, reviewer_id],
            ),
            actor,
        )
        assert decision.title == "Use capability declarations"
        assert decision.decision_markdown == "  **Preserve** this markdown.\n"
        assert [(row.user_id, row.status.value) for row in decision.reviewers] == [
            (reviewer_id, "pending")
        ]

        with pytest.raises(AppError) as error:
            service.review_decision(
                decision.id,
                DecisionReviewWrite(status="approved", expected_version=1),
                session.get(User, outsider_id),
            )
        assert error.value.code == "decision_reviewer_required"

        reviewed = service.review_decision(
            decision.id,
            DecisionReviewWrite(
                status="approved", comment="Looks good", expected_version=1
            ),
            reviewer,
        )
        assert reviewed.version == 2
        finalized = service.finalize_decision(
            decision.id, DecisionFinalizeWrite(expected_version=2), actor
        )
        assert finalized.status.value == "final"
        assert finalized.reviewers[0].status.value == "approved"


def test_final_decision_can_be_superseded_without_losing_history(
    client, outcome_context
):
    admin_id, _, _, project_id, _, _, _, _ = outcome_context
    with client.app.state.database.session() as session:
        service = OutcomeService(session)
        actor = session.get(User, admin_id)
        old = service.create_decision(
            project_id,
            DecisionWrite(title="Old", decision_markdown="Old answer"),
            actor,
        )
        old = service.finalize_decision(
            old.id, DecisionFinalizeWrite(expected_version=1), actor
        )
        new = service.create_decision(
            project_id,
            DecisionWrite(title="New", decision_markdown="New answer"),
            actor,
        )
        new = service.finalize_decision(
            new.id, DecisionFinalizeWrite(expected_version=1), actor
        )
        linked = service.supersede_decision(
            old.id,
            DecisionSupersedeWrite(
                new_decision_id=new.id,
                expected_version=old.version,
                expected_new_version=new.version,
            ),
            actor,
        )
        assert session.get(Decision, old.id).status.value == "superseded"
        assert linked.supersedes_decision_id == old.id


def test_source_validation_distinguishes_missing_and_mismatch(client, outcome_context):
    admin_id, _, _, project_id, _, future_id, agenda_id, _ = outcome_context
    with client.app.state.database.session() as session:
        service = OutcomeService(session)
        actor = session.get(User, admin_id)
        with pytest.raises(AppError) as missing:
            service.create_action(
                project_id,
                ActionWrite(meeting_id="missing", content="Do it"),
                actor,
            )
        assert missing.value.code == "source_not_found"
        with pytest.raises(AppError) as mismatch:
            service.create_action(
                project_id,
                ActionWrite(
                    meeting_id=future_id,
                    agenda_item_id=agenda_id,
                    content="Do it",
                ),
                actor,
            )
        assert mismatch.value.code == "source_mismatch"


def test_action_completion_and_reopening_manage_timestamp(client, outcome_context):
    admin_id, _, _, project_id, _, _, _, _ = outcome_context
    with client.app.state.database.session() as session:
        service = OutcomeService(session)
        actor = session.get(User, admin_id)
        action = service.create_action(
            project_id, ActionWrite(content="Ship it", priority="urgent"), actor
        )
        done = service.update_action(
            action.id, ActionEdit(expected_version=1, status="done"), actor
        )
        assert done.completed_at is not None
        reopened = service.update_action(
            action.id, ActionEdit(expected_version=2, status="in_progress"), actor
        )
        assert reopened.completed_at is None


def test_edit_schemas_reject_null_nonnullable_fields_and_blank_markdown():
    for payload in (
        lambda: ActionEdit(expected_version=1, content=None),
        lambda: ActionEdit(expected_version=1, status=None),
        lambda: DecisionWrite(title="D", decision_markdown="   "),
        lambda: QuestionWrite(question_markdown="\n  "),
    ):
        with pytest.raises(ValidationError):
            payload()


def test_concurrent_action_edit_has_exact_conflict_and_reusable_session(
    client, outcome_context
):
    admin_id, _, _, project_id, _, _, _, _ = outcome_context
    database = client.app.state.database
    with database.session() as seed:
        action = OutcomeService(seed).create_action(
            project_id,
            ActionWrite(content="Original"),
            seed.get(User, admin_id),
        )
        action_id = action.id

    with database.session() as first, database.session() as second:
        first_action = first.get(ActionItem, action_id)
        second_action = second.get(ActionItem, action_id)
        assert first_action.version == second_action.version == 1
        OutcomeService(first).update_action(
            action_id,
            ActionEdit(expected_version=1, content="First"),
            first.get(User, admin_id),
        )
        with pytest.raises(AppError) as conflict:
            OutcomeService(second).update_action(
                action_id,
                ActionEdit(expected_version=1, content="Second"),
                second.get(User, admin_id),
            )
        assert conflict.value.code == "version_conflict"
        assert conflict.value.details == {
            "expected_version": 1,
            "actual_version": 2,
        }
        assert (
            second.scalar(select(ActionItem.content).where(ActionItem.id == action_id))
            == "First"
        )


def test_question_schedule_and_resolve_are_idempotency_safe(client, outcome_context):
    admin_id, _, _, project_id, _, future_id, _, _ = outcome_context
    with client.app.state.database.session() as session:
        service = OutcomeService(session)
        actor = session.get(User, admin_id)
        question = service.create_question(
            project_id,
            QuestionWrite(question_markdown="What should we ship?"),
            actor,
        )
        future = session.get(Meeting, future_id)
        agenda = service.schedule_question(
            question.id,
            QuestionScheduleWrite(
                meeting_id=future_id,
                expected_version=1,
                expected_meeting_version=future.version,
            ),
            actor,
        )
        assert agenda.carry_from_open_question_id == question.id
        assert question.status.value == "scheduled"
        with pytest.raises(AppError) as duplicate:
            service.schedule_question(
                question.id,
                QuestionScheduleWrite(
                    meeting_id=future_id,
                    expected_version=question.version,
                    expected_meeting_version=future.version,
                ),
                actor,
            )
        assert duplicate.value.code == "question_already_scheduled"

        decision = service.create_decision(
            project_id,
            DecisionWrite(title="Answer", decision_markdown="Ship MeetFlow."),
            actor,
        )
        service.finalize_decision(
            decision.id, DecisionFinalizeWrite(expected_version=1), actor
        )
        resolved = service.resolve_question(
            question.id,
            QuestionResolveWrite(
                decision_id=decision.id, expected_version=question.version
            ),
            actor,
        )
        assert resolved.status.value == "resolved"
        assert resolved.resolved_by_decision_id == decision.id


def test_agenda_delete_guard_and_explicit_migration(client, outcome_context):
    admin_id, _, _, project_id, meeting_id, _, agenda_id, target_id = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        outcomes = OutcomeService(session)
        outcomes.create_decision(
            project_id,
            DecisionWrite(
                meeting_id=meeting_id,
                agenda_item_id=agenda_id,
                title="Decision",
                decision_markdown="D",
            ),
            actor,
        )
        outcomes.create_action(
            project_id,
            ActionWrite(meeting_id=meeting_id, agenda_item_id=agenda_id, content="A"),
            actor,
        )
        outcomes.create_question(
            project_id,
            QuestionWrite(
                meeting_id=meeting_id,
                agenda_item_id=agenda_id,
                question_markdown="Q?",
            ),
            actor,
        )
        source = session.get(AgendaItem, agenda_id)
        meeting = session.get(Meeting, meeting_id)
        with pytest.raises(AppError) as guarded:
            AgendaService(session).delete(
                agenda_id,
                AgendaCommand(expected_version=source.version),
                actor,
                expected_meeting_version=meeting.version,
            )
        assert guarded.value.code == "agenda_has_outcomes"

        other_project = ProjectService(session).create(
            ProjectWrite(
                name="Other project",
                slug="other-outcome-project",
                status="active",
                lead_user_id=actor.id,
                member_ids=[actor.id],
            ),
            actor,
        )
        other_meeting = MeetingService(session).create_meeting(
            other_project.id,
            MeetingWrite(
                title="Other meeting",
                scheduled_start=START + timedelta(days=14),
                scheduled_end=START + timedelta(days=14, hours=1),
            ),
            actor,
        )
        other_agenda = AgendaService(session).create(
            other_meeting.id,
            AgendaWrite(title="Other agenda", agenda_type="discussion"),
            actor,
            expected_meeting_version=other_meeting.version,
        )
        with pytest.raises(AppError) as cross_project:
            outcomes.migrate_agenda_outcomes(
                agenda_id,
                AgendaOutcomeMigrationWrite(
                    target_agenda_item_id=other_agenda.id,
                    expected_source_version=source.version,
                    expected_target_version=other_agenda.version,
                    expected_source_meeting_version=meeting.version,
                    expected_target_meeting_version=other_meeting.version,
                ),
                actor,
            )
        assert cross_project.value.code == "source_mismatch"
        assert session.scalar(select(Decision)).agenda_item_id == agenda_id
        assert session.scalar(select(ActionItem)).agenda_item_id == agenda_id
        assert session.scalar(select(OpenQuestion)).agenda_item_id == agenda_id

        outcomes.migrate_agenda_outcomes(
            agenda_id,
            AgendaOutcomeMigrationWrite(
                target_agenda_item_id=target_id,
                expected_source_version=source.version,
                expected_target_version=1,
                expected_source_meeting_version=meeting.version,
                expected_target_meeting_version=meeting.version,
            ),
            actor,
        )
        assert session.scalar(select(Decision)).agenda_item_id == target_id
        assert session.scalar(select(ActionItem)).agenda_item_id == target_id
        assert session.scalar(select(OpenQuestion)).agenda_item_id == target_id
        assert meeting.version == 4


def test_skipped_agenda_conversion_and_copy_are_explicit_and_duplicate_safe(
    client, outcome_context
):
    admin_id, _, _, project_id, meeting_id, future_id, agenda_id, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        agenda_service = AgendaService(session)
        source = session.get(AgendaItem, agenda_id)
        agenda_service.skip(
            agenda_id, AgendaCommand(expected_version=source.version), actor
        )
        source = session.get(AgendaItem, agenda_id)
        service = OutcomeService(session)
        question = service.convert_agenda_to_question(
            agenda_id,
            AgendaConvertWrite(expected_source_version=source.version),
            actor,
        )
        assert question.question_markdown == source.title
        with pytest.raises(AppError) as duplicate:
            service.convert_agenda_to_question(
                agenda_id,
                AgendaConvertWrite(expected_source_version=source.version),
                actor,
            )
        assert duplicate.value.code == "agenda_already_converted"

        future = session.get(Meeting, future_id)
        copied = service.copy_agenda_to_meeting(
            agenda_id,
            AgendaCopyWrite(
                target_meeting_id=future_id,
                expected_source_version=source.version,
                expected_target_meeting_version=future.version,
            ),
            actor,
        )
        assert copied.meeting_id == future_id
        with pytest.raises(AppError) as copied_twice:
            service.copy_agenda_to_meeting(
                agenda_id,
                AgendaCopyWrite(
                    target_meeting_id=future_id,
                    expected_source_version=source.version,
                    expected_target_meeting_version=future.version,
                ),
                actor,
            )
        assert copied_twice.value.code == "agenda_already_copied"


def test_outcome_routes_require_auth_and_return_serialized_lists(
    client, authenticated_client, outcome_context
):
    _, reviewer_id, _, project_id, meeting_id, _, agenda_id, _ = outcome_context
    unauthenticated = client.__class__(client.app)
    with unauthenticated:
        assert (
            unauthenticated.get(f"/api/projects/{project_id}/decisions").status_code
            == 401
        )

    created = authenticated_client.post(
        f"/api/projects/{project_id}/decisions",
        json={
            "meeting_id": meeting_id,
            "agenda_item_id": agenda_id,
            "title": "API decision",
            "decision_markdown": "**Decision**",
            "reviewer_ids": [reviewer_id],
        },
    )
    assert created.status_code == 201
    assert created.json()["reviewers"][0]["status"] == "pending"
    listed = authenticated_client.get(f"/api/projects/{project_id}/decisions")
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "API decision"
