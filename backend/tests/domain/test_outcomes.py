from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
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
    OpenQuestion,
    OutcomeMigrationRecord,
)
from app.outcomes.schemas import (
    ActionEdit,
    ActionWrite,
    AgendaConvertWrite,
    AgendaOutcomeMigrationWrite,
    DecisionFinalizeWrite,
    DecisionEdit,
    DecisionReviewWrite,
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
