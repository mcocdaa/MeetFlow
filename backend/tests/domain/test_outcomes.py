from datetime import datetime, timedelta, timezone
from typing import Literal

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.models import AgendaItem
from app.agendas.schemas import AgendaCommand, AgendaWrite
from app.agendas.service import AgendaService
from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.meetings.models import Meeting
from app.meetings.schemas import MeetingWrite
from app.meetings.service import MeetingService
from app.outcomes.models import (
    ActionItem,
    Decision,
    DecisionReviewer,
    OpenQuestion,
    OutcomeMigrationRecord,
)
from app.outcomes.schemas import (
    ActionEdit,
    ActionWrite,
    AgendaCopyWrite,
    AgendaConvertWrite,
    AgendaOutcomeMigrationWrite,
    DecisionFinalizeWrite,
    DecisionEdit,
    DecisionReviewWrite,
    DecisionSupersedeWrite,
    DecisionWrite,
    QuestionResolveWrite,
    QuestionEdit,
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


def test_decision_edit_finalize_pending_and_withdraw_preserve_history(
    client, outcome_context
):
    admin_id, reviewer_id, outsider_id, project_id, _, _, _, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        service = OutcomeService(session)
        decision = service.create_decision(
            project_id,
            DecisionWrite(
                title="Draft",
                decision_markdown="Exact markdown",
                reviewer_ids=[reviewer_id, outsider_id],
            ),
            actor,
        )
        edited = service.update_decision(
            decision.id,
            DecisionEdit(expected_version=1, title="Edited"),
            actor,
        )
        final = service.finalize_decision(
            edited.id, DecisionFinalizeWrite(expected_version=2), actor
        )
        assert final.title == "Edited"
        assert [row.status.value for row in final.reviewers] == ["pending", "pending"]

        withdrawn = service.create_decision(
            project_id,
            DecisionWrite(title="Withdraw", decision_markdown="No longer valid"),
            actor,
        )
        withdrawn = service.withdraw_decision(
            withdrawn.id, DecisionFinalizeWrite(expected_version=1), actor
        )
        assert withdrawn.status.value == "withdrawn"


def test_decision_edit_retains_responded_reviewers_but_can_remove_pending(
    client, outcome_context
):
    admin_id, reviewer_id, outsider_id, project_id, _, _, _, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        reviewer = session.get(User, reviewer_id)
        service = OutcomeService(session)
        decision = service.create_decision(
            project_id,
            DecisionWrite(
                title="Review history",
                decision_markdown="D",
                reviewer_ids=[reviewer_id, outsider_id],
            ),
            actor,
        )
        reviewed = service.review_decision(
            decision.id,
            DecisionReviewWrite(
                status="changes_requested",
                comment="Keep this response",
                expected_version=1,
            ),
            reviewer,
        )
        response_time = next(
            row.responded_at for row in reviewed.reviewers if row.user_id == reviewer_id
        )
        edited = service.update_decision(
            decision.id,
            DecisionEdit(expected_version=2, reviewer_ids=[]),
            actor,
        )
        assert len(edited.reviewers) == 1
        retained = edited.reviewers[0]
        assert retained.user_id == reviewer_id
        assert retained.status.value == "changes_requested"
        assert retained.comment == "Keep this response"
        assert retained.responded_at == response_time
        finalized = service.finalize_decision(
            decision.id, DecisionFinalizeWrite(expected_version=3), actor
        )
        assert finalized.reviewers[0].responded_at == response_time


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
                ActionWrite(
                    project_id=project_id, meeting_id="missing", content="Do it"
                ),
                actor,
            )
        assert missing.value.code == "source_not_found"
        with pytest.raises(AppError) as mismatch:
            service.create_action(
                project_id,
                ActionWrite(
                    project_id=project_id,
                    meeting_id=future_id,
                    agenda_item_id=agenda_id,
                    content="Do it",
                ),
                actor,
            )
        assert mismatch.value.code == "source_mismatch"


def test_invalid_or_inactive_owner_does_not_poison_session(client, outcome_context):
    admin_id, _, _, project_id, _, _, _, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        inactive = User(
            username="inactive-owner",
            display_name="Inactive",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.DISABLED,
        )
        session.add(inactive)
        session.commit()
        service = OutcomeService(session)
        for owner_id in ("missing-user", inactive.id):
            with pytest.raises(AppError) as error:
                service.create_action(
                    project_id,
                    ActionWrite(
                        project_id=project_id,
                        content="Owned task",
                        owner_user_id=owner_id,
                    ),
                    actor,
                )
            assert error.value.code == "user_not_found"
            assert (
                session.scalar(select(User.id).where(User.id == actor.id)) == actor.id
            )


def test_action_completion_and_reopening_manage_timestamp(client, outcome_context):
    admin_id, _, _, project_id, _, _, _, _ = outcome_context
    with client.app.state.database.session() as session:
        service = OutcomeService(session)
        actor = session.get(User, admin_id)
        action = service.create_action(
            project_id,
            ActionWrite(project_id=project_id, content="Ship it", priority="urgent"),
            actor,
        )
        done = service.update_action(
            action.id, ActionEdit(expected_version=1, status="done"), actor
        )
        assert done.completed_at is not None
        reopened = service.update_action(
            action.id, ActionEdit(expected_version=2, status="in_progress"), actor
        )
        assert reopened.completed_at is None


def test_action_noops_and_done_edits_preserve_completion_timestamp(
    client, outcome_context
):
    admin_id, _, _, project_id, _, _, _, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        service = OutcomeService(session)
        action = service.create_action(
            project_id,
            ActionWrite(project_id=project_id, content="Ship"),
            actor,
        )
        done = service.update_action(
            action.id, ActionEdit(expected_version=1, status="done"), actor
        )
        completed_at = done.completed_at
        repeated = service.update_action(
            action.id, ActionEdit(expected_version=2, status="done"), actor
        )
        assert repeated.version == 2
        assert repeated.completed_at == completed_at
        edited = service.update_action(
            action.id,
            ActionEdit(expected_version=2, content="Ship with notes"),
            actor,
        )
        assert edited.version == 3
        assert edited.completed_at == completed_at
        unchanged = service.update_action(
            action.id,
            ActionEdit(expected_version=3, content="Ship with notes"),
            actor,
        )
        assert unchanged.version == 3
        assert unchanged.completed_at == completed_at


def test_edit_schemas_reject_null_nonnullable_fields_and_blank_markdown():
    for payload in (
        lambda: ActionEdit(expected_version=1, content=None),
        lambda: ActionEdit(expected_version=1, status=None),
        lambda: DecisionWrite(title="D", decision_markdown="   "),
        lambda: QuestionWrite(question_markdown="\n  "),
    ):
        with pytest.raises(ValidationError):
            payload()


def test_outcome_contracts_normalize_refs_and_forbid_status_bypass():
    assert (
        ActionWrite.model_fields["priority"].annotation
        == Literal["low", "normal", "high", "urgent"]
    )
    with pytest.raises(ValidationError):
        ActionWrite(content="Missing project")
    with pytest.raises(ValidationError):
        DecisionReviewWrite(status="pending", expected_version=1)
    with pytest.raises(ValidationError):
        QuestionEdit(expected_version=1, status="resolved")

    assert ActionWrite(project_id="  p1  ", content="Do").project_id == "p1"
    assert ActionEdit(expected_version=1, owner_user_id="  u1 ").owner_user_id == "u1"
    assert ActionEdit(expected_version=1, owner_user_id=None).owner_user_id is None
    assert (
        QuestionWrite(question_markdown="Q?", owner_user_id="  u2 ").owner_user_id
        == "u2"
    )
    assert (
        QuestionScheduleWrite(
            meeting_id="  m1 ", expected_version=1, expected_meeting_version=1
        ).meeting_id
        == "m1"
    )
    assert (
        QuestionResolveWrite(decision_id="  d1 ", expected_version=1).decision_id
        == "d1"
    )
    assert (
        DecisionSupersedeWrite(
            new_decision_id="  d2 ", expected_version=1, expected_new_version=1
        ).new_decision_id
        == "d2"
    )
    for factory in (
        lambda: ActionEdit(expected_version=1, owner_user_id="   "),
        lambda: QuestionWrite(question_markdown="Q", owner_user_id="   "),
        lambda: QuestionScheduleWrite(
            meeting_id="   ", expected_version=1, expected_meeting_version=1
        ),
        lambda: QuestionResolveWrite(decision_id="   ", expected_version=1),
    ):
        with pytest.raises(ValidationError):
            factory()


def test_outcome_models_have_exact_duplicate_keys_and_migration_audit():
    assert OpenQuestion.__table__.c.converted_from_agenda_item_id.unique
    assert "copied_from_agenda_item_id" in AgendaItem.__table__.c
    copied_unique = {
        tuple(column.name for column in constraint.columns)
        for constraint in AgendaItem.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("meeting_id", "copied_from_agenda_item_id") in copied_unique
    assert DecisionReviewer.__table__.c.comment.nullable
    assert "outcome_migration_records" in Decision.metadata.tables


def test_concurrent_action_edit_has_exact_conflict_and_reusable_session(
    client, outcome_context
):
    admin_id, _, _, project_id, _, _, _, _ = outcome_context
    database = client.app.state.database
    with database.session() as seed:
        action = OutcomeService(seed).create_action(
            project_id,
            ActionWrite(project_id=project_id, content="Original"),
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


def test_project_question_rejects_past_and_immutable_schedule_targets(
    client, outcome_context
):
    admin_id, _, _, project_id, _, future_id, _, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        meetings = MeetingService(session)
        past = meetings.create_meeting(
            project_id,
            MeetingWrite(
                title="Past meeting",
                scheduled_start=START - timedelta(days=60),
                scheduled_end=START - timedelta(days=60) + timedelta(hours=1),
            ),
            actor,
        )
        service = OutcomeService(session)
        question = service.create_question(
            project_id, QuestionWrite(question_markdown="When?"), actor
        )
        with pytest.raises(AppError) as past_error:
            service.schedule_question(
                question.id,
                QuestionScheduleWrite(
                    meeting_id=past.id,
                    expected_version=question.version,
                    expected_meeting_version=past.version,
                ),
                actor,
            )
        assert past_error.value.code == "meeting_not_future"

        future = session.get(Meeting, future_id)
        future.status = "completed"
        future.version += 1
        session.commit()
        with pytest.raises(AppError) as immutable:
            service.schedule_question(
                question.id,
                QuestionScheduleWrite(
                    meeting_id=future.id,
                    expected_version=question.version,
                    expected_meeting_version=future.version,
                ),
                actor,
            )
        assert immutable.value.code == "meeting_immutable"


@pytest.mark.parametrize("terminal_status", ["completed", "canceled"])
def test_terminal_meeting_rejects_all_meeting_linked_outcome_creation(
    client, outcome_context, terminal_status
):
    admin_id, _, _, project_id, meeting_id, _, agenda_id, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        service = OutcomeService(session)
        existing_action = service.create_action(
            project_id,
            ActionWrite(
                project_id=project_id,
                meeting_id=meeting_id,
                agenda_item_id=agenda_id,
                content="Existing action",
            ),
            actor,
        )
        meeting = session.get(Meeting, meeting_id)
        meeting.status = terminal_status
        meeting.version += 1
        session.commit()
        calls = (
            lambda: service.create_decision(
                project_id,
                DecisionWrite(
                    meeting_id=meeting_id,
                    agenda_item_id=agenda_id,
                    title="Blocked",
                    decision_markdown="D",
                ),
                actor,
            ),
            lambda: service.create_action(
                project_id,
                ActionWrite(
                    project_id=project_id,
                    meeting_id=meeting_id,
                    agenda_item_id=agenda_id,
                    content="Blocked",
                ),
                actor,
            ),
            lambda: service.create_question(
                project_id,
                QuestionWrite(
                    meeting_id=meeting_id,
                    agenda_item_id=agenda_id,
                    question_markdown="Blocked?",
                ),
                actor,
            ),
        )
        for call in calls:
            with pytest.raises(AppError) as error:
                call()
            assert error.value.code == "meeting_immutable"
        assert session.scalar(select(func.count(Decision.id))) == 0
        assert session.scalar(select(func.count(ActionItem.id))) == 1
        assert session.scalar(select(func.count(OpenQuestion.id))) == 0
        updated = service.update_action(
            existing_action.id,
            ActionEdit(expected_version=1, content="Still editable"),
            actor,
        )
        assert updated.content == "Still editable"


def test_terminal_meeting_rejects_migration_and_convert_without_partial_changes(
    client, outcome_context
):
    admin_id, _, _, project_id, meeting_id, _, source_id, target_id = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        agenda_service = AgendaService(session)
        source = session.get(AgendaItem, source_id)
        agenda_service.skip(
            source.id, AgendaCommand(expected_version=source.version), actor
        )
        service = OutcomeService(session)
        decision = service.create_decision(
            project_id,
            DecisionWrite(
                meeting_id=meeting_id,
                agenda_item_id=source_id,
                title="Must stay",
                decision_markdown="D",
            ),
            actor,
        )
        meeting = session.get(Meeting, meeting_id)
        meeting.status = "completed"
        meeting.version += 1
        session.commit()
        source = session.get(AgendaItem, source_id)
        target = session.get(AgendaItem, target_id)
        with pytest.raises(AppError) as migration:
            service.migrate_agenda_outcomes(
                source_id,
                AgendaOutcomeMigrationWrite(
                    target_agenda_item_id=target_id,
                    expected_source_version=source.version,
                    expected_target_version=target.version,
                    expected_source_meeting_version=meeting.version,
                    expected_target_meeting_version=meeting.version,
                ),
                actor,
            )
        assert migration.value.code == "meeting_immutable"
        assert session.get(Decision, decision.id).agenda_item_id == source_id
        with pytest.raises(AppError) as conversion:
            service.convert_agenda_to_question(
                source_id,
                AgendaConvertWrite(
                    expected_source_version=source.version,
                    expected_source_meeting_version=meeting.version,
                ),
                actor,
            )
        assert conversion.value.code == "meeting_immutable"
        assert session.scalar(select(func.count(OpenQuestion.id))) == 0


def test_terminal_target_meeting_rejects_migration_and_copy_without_partial_changes(
    client, outcome_context
):
    admin_id, _, _, project_id, meeting_id, future_id, source_id, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        service = OutcomeService(session)
        decision = service.create_decision(
            project_id,
            DecisionWrite(
                meeting_id=meeting_id,
                agenda_item_id=source_id,
                title="Stay at source",
                decision_markdown="D",
            ),
            actor,
        )
        source = session.get(AgendaItem, source_id)
        AgendaService(session).skip(
            source.id, AgendaCommand(expected_version=source.version), actor
        )
        future = session.get(Meeting, future_id)
        target = AgendaService(session).create(
            future_id,
            AgendaWrite(title="Terminal target", agenda_type="discussion"),
            actor,
            expected_meeting_version=future.version,
        )
        future.status = "canceled"
        future.version += 1
        session.commit()
        source = session.get(AgendaItem, source_id)
        source_meeting = session.get(Meeting, meeting_id)
        with pytest.raises(AppError) as migration:
            service.migrate_agenda_outcomes(
                source_id,
                AgendaOutcomeMigrationWrite(
                    target_agenda_item_id=target.id,
                    expected_source_version=source.version,
                    expected_target_version=target.version,
                    expected_source_meeting_version=source_meeting.version,
                    expected_target_meeting_version=future.version,
                ),
                actor,
            )
        assert migration.value.code == "meeting_immutable"
        assert session.get(Decision, decision.id).agenda_item_id == source_id
        with pytest.raises(AppError) as copied:
            service.copy_agenda_to_meeting(
                source_id,
                AgendaCopyWrite(
                    target_meeting_id=future_id,
                    expected_source_version=source.version,
                    expected_source_meeting_version=source_meeting.version,
                    expected_target_meeting_version=future.version,
                ),
                actor,
            )
        assert copied.value.code == "meeting_immutable"
        assert (
            session.scalar(
                select(func.count(AgendaItem.id)).where(
                    AgendaItem.copied_from_agenda_item_id == source_id
                )
            )
            == 0
        )


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
            ActionWrite(
                project_id=project_id,
                meeting_id=meeting_id,
                agenda_item_id=agenda_id,
                content="A",
            ),
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
        # Each meeting-bound outcome creation and the migration advance the
        # parent revision, so completion cannot race any of these writes.
        assert meeting.version == 7
        audit = session.scalar(select(OutcomeMigrationRecord))
        assert outcomes.list_migration_records(agenda_id)[0].id == audit.id
        assert audit.source_agenda_id == agenda_id
        assert audit.source_meeting_id == meeting_id
        assert audit.target_agenda_id == target_id
        assert {row["type"] for row in audit.moved_outcomes_json} == {
            "decision",
            "action",
            "open_question",
        }
        assert all(
            row["old_agenda_item_id"] == agenda_id
            and row["old_meeting_id"] == meeting_id
            for row in audit.moved_outcomes_json
        )
        AgendaService(session).delete(
            agenda_id,
            AgendaCommand(expected_version=source.version),
            actor,
            expected_meeting_version=meeting.version,
        )
        assert session.get(AgendaItem, agenda_id) is None


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
        source_meeting = session.get(Meeting, meeting_id)
        service = OutcomeService(session)
        question = service.convert_agenda_to_question(
            agenda_id,
            AgendaConvertWrite(
                expected_source_version=source.version,
                expected_source_meeting_version=source_meeting.version,
            ),
            actor,
        )
        assert question.question_markdown == source.title
        assert question.converted_from_agenda_item_id == source.id
        with pytest.raises(AppError) as duplicate:
            service.convert_agenda_to_question(
                agenda_id,
                AgendaConvertWrite(
                    expected_source_version=1,
                    expected_source_meeting_version=1,
                ),
                actor,
            )
        assert duplicate.value.code == "agenda_already_converted"

        future = session.get(Meeting, future_id)
        unrelated = AgendaService(session).create(
            future.id,
            AgendaWrite(title=source.title, agenda_type=source.agenda_type),
            actor,
            expected_meeting_version=future.version,
        )
        assert unrelated.title == source.title
        source_version = source.version
        source_meeting_version = source_meeting.version
        copied = service.copy_agenda_to_meeting(
            agenda_id,
            AgendaCopyWrite(
                target_meeting_id=future_id,
                expected_source_version=source_version,
                expected_source_meeting_version=source_meeting_version,
                expected_target_meeting_version=future.version,
            ),
            actor,
        )
        assert copied.meeting_id == future_id
        assert copied.copied_from_agenda_item_id == source.id
        with pytest.raises(AppError) as copied_twice:
            service.copy_agenda_to_meeting(
                agenda_id,
                AgendaCopyWrite(
                    target_meeting_id=future_id,
                    expected_source_version=1,
                    expected_source_meeting_version=1,
                    expected_target_meeting_version=1,
                ),
                actor,
            )
        assert copied_twice.value.code == "agenda_already_copied"


def test_concurrent_convert_and_copy_map_to_stable_duplicate_errors(
    client, outcome_context
):
    admin_id, _, _, _, meeting_id, future_id, agenda_id, _ = outcome_context
    database = client.app.state.database
    with database.session() as seed:
        actor = seed.get(User, admin_id)
        source = seed.get(AgendaItem, agenda_id)
        AgendaService(seed).skip(
            source.id, AgendaCommand(expected_version=source.version), actor
        )

    with database.session() as first, database.session() as second:
        first_source = first.get(AgendaItem, agenda_id)
        second_source = second.get(AgendaItem, agenda_id)
        first_meeting = first.get(Meeting, meeting_id)
        second_meeting = second.get(Meeting, meeting_id)
        convert = AgendaConvertWrite(
            expected_source_version=first_source.version,
            expected_source_meeting_version=first_meeting.version,
        )
        OutcomeService(first).convert_agenda_to_question(
            agenda_id, convert, first.get(User, admin_id)
        )
        with pytest.raises(AppError) as duplicate:
            OutcomeService(second).convert_agenda_to_question(
                agenda_id,
                AgendaConvertWrite(
                    expected_source_version=second_source.version,
                    expected_source_meeting_version=second_meeting.version,
                ),
                second.get(User, admin_id),
            )
        assert duplicate.value.code == "agenda_already_converted"
        assert second.scalar(select(OpenQuestion.id)) is not None

    with database.session() as first, database.session() as second:
        first_source = first.get(AgendaItem, agenda_id)
        second_source = second.get(AgendaItem, agenda_id)
        first_source_meeting = first.get(Meeting, meeting_id)
        second_source_meeting = second.get(Meeting, meeting_id)
        first_target = first.get(Meeting, future_id)
        second_target = second.get(Meeting, future_id)
        OutcomeService(first).copy_agenda_to_meeting(
            agenda_id,
            AgendaCopyWrite(
                target_meeting_id=future_id,
                expected_source_version=first_source.version,
                expected_source_meeting_version=first_source_meeting.version,
                expected_target_meeting_version=first_target.version,
            ),
            first.get(User, admin_id),
        )
        with pytest.raises(AppError) as duplicate:
            OutcomeService(second).copy_agenda_to_meeting(
                agenda_id,
                AgendaCopyWrite(
                    target_meeting_id=future_id,
                    expected_source_version=second_source.version,
                    expected_source_meeting_version=second_source_meeting.version,
                    expected_target_meeting_version=second_target.version,
                ),
                second.get(User, admin_id),
            )
        assert duplicate.value.code == "agenda_already_copied"
        assert second.scalar(
            select(AgendaItem.id).where(
                AgendaItem.meeting_id == future_id,
                AgendaItem.copied_from_agenda_item_id == agenda_id,
            )
        )


@pytest.mark.parametrize("command", ["convert", "copy"])
def test_nonduplicate_integrity_errors_are_not_mislabeled_as_version_conflicts(
    client, outcome_context, monkeypatch, command
):
    admin_id, _, _, _, meeting_id, future_id, source_id, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        source = session.get(AgendaItem, source_id)
        AgendaService(session).skip(
            source.id, AgendaCommand(expected_version=source.version), actor
        )
        source = session.get(AgendaItem, source_id)
        source_meeting = session.get(Meeting, meeting_id)
        future = session.get(Meeting, future_id)

        def fail_integrity():
            raise IntegrityError("INSERT", {}, RuntimeError("foreign key failure"))

        monkeypatch.setattr(session, "commit", fail_integrity)
        service = OutcomeService(session)
        with pytest.raises(AppError) as error:
            if command == "convert":
                service.convert_agenda_to_question(
                    source_id,
                    AgendaConvertWrite(
                        expected_source_version=source.version,
                        expected_source_meeting_version=source_meeting.version,
                    ),
                    actor,
                )
            else:
                service.copy_agenda_to_meeting(
                    source_id,
                    AgendaCopyWrite(
                        target_meeting_id=future_id,
                        expected_source_version=source.version,
                        expected_source_meeting_version=source_meeting.version,
                        expected_target_meeting_version=future.version,
                    ),
                    actor,
                )
        assert error.value.code == "outcome_integrity_conflict"
        assert session.scalar(select(AgendaItem.id).where(AgendaItem.id == source_id))


def test_convert_stale_write_maps_exact_version_conflict_and_recovers_session(
    client, outcome_context, monkeypatch
):
    admin_id, _, _, _, meeting_id, _, source_id, _ = outcome_context
    database = client.app.state.database
    with database.session() as session:
        actor = session.get(User, admin_id)
        source = session.get(AgendaItem, source_id)
        AgendaService(session).skip(
            source.id, AgendaCommand(expected_version=source.version), actor
        )
        source = session.get(AgendaItem, source_id)
        source_meeting = session.get(Meeting, meeting_id)
        expected_source_version = source.version

        def fail_stale():
            with database.session() as competing:
                competing_source = competing.get(AgendaItem, source_id)
                competing_source.version += 1
                competing.commit()
            raise StaleDataError("concurrent agenda update")

        monkeypatch.setattr(session, "commit", fail_stale)
        with pytest.raises(AppError) as conflict:
            OutcomeService(session).convert_agenda_to_question(
                source_id,
                AgendaConvertWrite(
                    expected_source_version=expected_source_version,
                    expected_source_meeting_version=source_meeting.version,
                ),
                actor,
            )
        assert conflict.value.code == "version_conflict"
        assert conflict.value.details == {
            "expected_version": expected_source_version,
            "actual_version": expected_source_version + 1,
        }
        assert session.scalar(select(AgendaItem.id).where(AgendaItem.id == source_id))


def test_concurrent_migration_rolls_back_and_leaves_session_reusable(
    client, outcome_context
):
    admin_id, _, _, project_id, meeting_id, _, source_id, target_id = outcome_context
    database = client.app.state.database
    with database.session() as seed:
        actor = seed.get(User, admin_id)
        service = OutcomeService(seed)
        decision = service.create_decision(
            project_id,
            DecisionWrite(
                meeting_id=meeting_id,
                agenda_item_id=source_id,
                title="Concurrent migration",
                decision_markdown="D",
            ),
            actor,
        )
        decision_id = decision.id

    with database.session() as first, database.session() as second:
        first_source = first.get(AgendaItem, source_id)
        second_source = second.get(AgendaItem, source_id)
        first_target = first.get(AgendaItem, target_id)
        second_target = second.get(AgendaItem, target_id)
        first_meeting = first.get(Meeting, meeting_id)
        second_meeting = second.get(Meeting, meeting_id)
        first_payload = AgendaOutcomeMigrationWrite(
            target_agenda_item_id=target_id,
            expected_source_version=first_source.version,
            expected_target_version=first_target.version,
            expected_source_meeting_version=first_meeting.version,
            expected_target_meeting_version=first_meeting.version,
        )
        OutcomeService(first).migrate_agenda_outcomes(
            source_id, first_payload, first.get(User, admin_id)
        )
        with pytest.raises(AppError) as conflict:
            OutcomeService(second).migrate_agenda_outcomes(
                source_id,
                AgendaOutcomeMigrationWrite(
                    target_agenda_item_id=target_id,
                    expected_source_version=second_source.version,
                    expected_target_version=second_target.version,
                    expected_source_meeting_version=second_meeting.version,
                    expected_target_meeting_version=second_meeting.version,
                ),
                second.get(User, admin_id),
            )
        assert conflict.value.code == "version_conflict"
        assert (
            second.scalar(
                select(Decision.agenda_item_id).where(Decision.id == decision_id)
            )
            == target_id
        )
        assert second.scalar(select(func.count(OutcomeMigrationRecord.id))) == 1


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
    assert (
        authenticated_client.get(
            f"/api/projects/{project_id}/decisions?limit=201"
        ).status_code
        == 422
    )

    mismatch = authenticated_client.post(
        f"/api/projects/{project_id}/actions",
        json={"project_id": "another-project", "content": "Mismatch"},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "source_mismatch"
    created_action = authenticated_client.post(
        f"/api/projects/{project_id}/actions",
        json={"project_id": project_id, "content": "API action"},
    )
    assert created_action.status_code == 201
    assert created_action.json()["project_id"] == project_id
    created_question = authenticated_client.post(
        f"/api/projects/{project_id}/open-questions",
        json={"question_markdown": "API question"},
    )
    assert created_question.status_code == 201
    assert created_question.json()["question_markdown"] == "API question"
    questions = authenticated_client.get(f"/api/projects/{project_id}/open-questions")
    assert questions.status_code == 200
    assert questions.json()[0]["id"] == created_question.json()["id"]


def test_decision_list_query_count_is_bounded(client, outcome_context):
    admin_id, _, _, project_id, _, _, _, _ = outcome_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        service = OutcomeService(session)
        for index in range(8):
            service.create_decision(
                project_id,
                DecisionWrite(title=f"Decision {index}", decision_markdown=f"D{index}"),
                actor,
            )
        statements = []

        def track(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        event.listen(session.bind, "before_cursor_execute", track)
        try:
            assert len(service.list_decisions(project_id, limit=8)) == 8
        finally:
            event.remove(session.bind, "before_cursor_execute", track)
        assert len(statements) <= 3


def test_every_outcome_route_is_authenticated(client):
    cases = (
        ("GET", "/api/projects/p/decisions", None),
        ("POST", "/api/projects/p/decisions", {"title": "D", "decision_markdown": "D"}),
        ("PUT", "/api/decisions/d", {"expected_version": 1, "title": "D"}),
        (
            "POST",
            "/api/decisions/d/review",
            {"expected_version": 1, "status": "approved"},
        ),
        ("POST", "/api/decisions/d/finalize", {"expected_version": 1}),
        ("POST", "/api/decisions/d/withdraw", {"expected_version": 1}),
        (
            "POST",
            "/api/decisions/d/supersede",
            {"new_decision_id": "n", "expected_version": 1, "expected_new_version": 1},
        ),
        ("GET", "/api/projects/p/actions", None),
        ("POST", "/api/projects/p/actions", {"project_id": "p", "content": "A"}),
        ("PUT", "/api/actions/a", {"expected_version": 1, "content": "A"}),
        ("GET", "/api/projects/p/open-questions", None),
        ("POST", "/api/projects/p/open-questions", {"question_markdown": "Q"}),
        (
            "PUT",
            "/api/open-questions/q",
            {"expected_version": 1, "question_markdown": "Q"},
        ),
        (
            "POST",
            "/api/open-questions/q/schedule",
            {"meeting_id": "m", "expected_version": 1, "expected_meeting_version": 1},
        ),
        ("POST", "/api/open-questions/q/resolve", {"expected_version": 1}),
        (
            "POST",
            "/api/agenda-items/a/migrate-outcomes",
            {
                "target_agenda_item_id": "b",
                "expected_source_version": 1,
                "expected_target_version": 1,
                "expected_source_meeting_version": 1,
                "expected_target_meeting_version": 1,
            },
        ),
        (
            "POST",
            "/api/agenda-items/a/convert-to-question",
            {"expected_source_version": 1, "expected_source_meeting_version": 1},
        ),
        (
            "POST",
            "/api/agenda-items/a/copy-to-meeting",
            {
                "target_meeting_id": "m",
                "expected_source_version": 1,
                "expected_source_meeting_version": 1,
                "expected_target_meeting_version": 1,
            },
        ),
    )
    unauthenticated = client.__class__(client.app)
    with unauthenticated:
        for method, path, body in cases:
            response = unauthenticated.request(method, path, json=body)
            assert response.status_code == 401, (method, path, response.text)
