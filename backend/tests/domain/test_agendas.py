from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from app.agendas.models import AgendaItem
from app.agendas.schemas import (
    AgendaCommand,
    AgendaEdit,
    AgendaMove,
    AgendaReorder,
    AgendaWrite,
)
from app.agendas.service import AgendaService
from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.meetings.models import Meeting
from app.meetings.schemas import LifecycleCommand, MeetingWrite
from app.meetings.service import MeetingService
from app.outcomes.models import ActionItem, Decision, OpenQuestion
from app.outcomes.schemas import ActionEdit, ActionWrite, DecisionEdit, QuestionEdit
from app.outcomes.service import OutcomeService
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService

START = datetime(2026, 7, 22, 9, tzinfo=timezone.utc)


@pytest.fixture
def agenda_context(client):
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        presenter = User(
            username="agenda-presenter",
            display_name="Agenda Presenter",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add(presenter)
        session.commit()
        project = ProjectService(session).create(
            ProjectWrite(
                name="Agenda domain",
                slug="agenda-domain",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id, presenter.id],
            ),
            admin,
        )
        meeting = MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Agenda review",
                scheduled_start=START,
                scheduled_end=START + timedelta(hours=1),
            ),
            admin,
        )
        session.refresh(admin)
        session.refresh(presenter)
        session.expunge(admin)
        session.expunge(presenter)
        return admin, presenter, meeting.id


def add_item(service, meeting, actor, title, position=None, **values):
    return service.create(
        meeting.id,
        AgendaWrite(
            title=title,
            agenda_type=values.pop("agenda_type", "discussion"),
            position=position,
            **values,
        ),
        actor,
        expected_meeting_version=meeting.version,
    )


def test_create_appends_and_inserts_with_contiguous_positions(client, agenda_context):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        first = add_item(service, meeting, admin, "  First  ")
        session.refresh(meeting)
        add_item(service, meeting, admin, "Third")
        session.refresh(meeting)
        middle = add_item(service, meeting, admin, "Middle", position=1)

        assert first.title == "First"
        assert [item.title for item in service.list(meeting_id)] == [
            "First",
            "Middle",
            "Third",
        ]
        assert [item.position for item in service.list(meeting_id)] == [0, 1, 2]
        assert middle.version == 1


def test_agenda_write_defaults_to_a_five_minute_estimate():
    assert AgendaWrite(title="Default estimate", agenda_type="discussion").estimated_minutes == 5


def test_complete_and_advance_starts_next_planned_without_finishing_other_started(
    client, agenda_context, monkeypatch
):
    admin, _, meeting_id = agenda_context
    first_at = datetime(2026, 8, 10, 9, tzinfo=timezone.utc)
    completed_at = datetime(2026, 8, 10, 9, 5, tzinfo=timezone.utc)
    monkeypatch.setattr("app.agendas.service.utcnow", lambda: completed_at)
    with client.app.state.database.session() as session:
        meetings = MeetingService(session)
        agendas = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        current = add_item(agendas, meeting, admin, "Current")
        session.refresh(meeting)
        already_open = add_item(agendas, meeting, admin, "Earlier open")
        session.refresh(meeting)
        next_item = add_item(agendas, meeting, admin, "Next")
        meetings.start(
            meeting_id,
            LifecycleCommand(expected_version=session.get(Meeting, meeting_id).version),
            admin,
        )
        current.started_at = first_at
        already_open.status = "in_progress"
        already_open.started_at = first_at
        session.commit()

        completed, next_id = agendas.complete_and_advance(
            current.id,
            AgendaCommand(expected_version=current.version),
            admin,
        )

        assert completed.status.value == "completed"
        assert completed.actual_duration_seconds == 300
        assert next_id == next_item.id
        assert session.get(AgendaItem, next_item.id).status.value == "in_progress"
        assert session.get(AgendaItem, already_open.id).status.value == "in_progress"


def test_complete_and_advance_returns_none_when_no_later_planned_item(
    client, agenda_context
):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        meetings = MeetingService(session)
        agendas = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        item = add_item(agendas, meeting, admin, "Only")
        meetings.start(
            meeting_id,
            LifecycleCommand(expected_version=session.get(Meeting, meeting_id).version),
            admin,
        )

        completed, next_id = agendas.complete_and_advance(
            item.id,
            AgendaCommand(expected_version=item.version),
            admin,
        )

        assert completed.status.value == "completed"
        assert next_id is None


def test_complete_and_advance_rejects_a_stale_item_without_starting_next(
    client, agenda_context
):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        meetings = MeetingService(session)
        agendas = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        current = add_item(agendas, meeting, admin, "Current")
        session.refresh(meeting)
        later = add_item(agendas, meeting, admin, "Later")
        meetings.start(
            meeting_id,
            LifecycleCommand(expected_version=session.get(Meeting, meeting_id).version),
            admin,
        )

        with pytest.raises(AppError) as error:
            agendas.complete_and_advance(
                current.id,
                AgendaCommand(expected_version=current.version + 1),
                admin,
            )

        assert error.value.code == "version_conflict"
        assert session.get(AgendaItem, current.id).status.value == "in_progress"
        assert session.get(AgendaItem, later.id).status.value == "planned"


def test_public_agenda_edit_reorder_transitions_and_parent_lock(client, agenda_context):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meetings = MeetingService(session)
        meeting = session.get(Meeting, meeting_id)
        first = add_item(service, meeting, admin, "First")
        session.refresh(meeting)
        second = add_item(service, meeting, admin, "Second")

        edited = service.update(
            first.id,
            AgendaEdit(expected_version=first.version, title="Updated first"),
            admin,
        )
        session.refresh(meeting)
        ordered = service.reorder(
            meeting_id,
            AgendaReorder(
                ids=[second.id, edited.id],
                expected_meeting_version=meeting.version,
            ),
            admin,
        )
        assert [item.title for item in ordered] == ["Second", "Updated first"]

        session.refresh(meeting)
        running = meetings.start(
            meeting_id, LifecycleCommand(expected_version=meeting.version), admin
        )
        started = service.start(
            edited.id, AgendaCommand(expected_version=edited.version), admin
        )
        completed = service.complete(
            edited.id, AgendaCommand(expected_version=started.version), admin
        )
        assert completed.status.value == "completed"

        canceled = meetings.cancel(
            meeting_id, LifecycleCommand(expected_version=running.version), admin
        )
        assert canceled.status.value == "canceled"
        with pytest.raises(AppError) as locked:
            service.update(
                second.id,
                AgendaEdit(expected_version=second.version, title="Too late"),
                admin,
            )
        assert locked.value.code == "meeting_immutable"


def test_saving_agenda_reconciles_tagged_outcomes_and_preserves_manual_rows(
    client, agenda_context
):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        agenda_service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        agenda = add_item(agenda_service, meeting, admin, "Delivery decision")
        manual = OutcomeService(session).create_action(
            meeting.project_id,
            ActionWrite(
                project_id=meeting.project_id,
                meeting_id=meeting.id,
                agenda_item_id=agenda.id,
                content="Manual follow-up",
            ),
            admin,
        )

        saved = agenda_service.update(
            agenda.id,
            AgendaEdit(
                expected_version=agenda.version,
                notes_markdown="@决策: 采用方案 A\n@行动: 发布\n@开放问题: 谁负责？",
            ),
            admin,
        )

        decisions = session.scalars(
            select(Decision).where(Decision.source_agenda_item_id == agenda.id)
        ).all()
        actions = session.scalars(
            select(ActionItem).where(ActionItem.source_agenda_item_id == agenda.id)
        ).all()
        questions = session.scalars(
            select(OpenQuestion).where(OpenQuestion.source_agenda_item_id == agenda.id)
        ).all()
        assert [(row.source_tag_key, row.decision_markdown) for row in decisions] == [
            ("decision:0", "采用方案 A")
        ]
        assert [(row.source_tag_key, row.content) for row in actions] == [
            ("action:0", "发布")
        ]
        assert [(row.source_tag_key, row.question_markdown) for row in questions] == [
            ("question:0", "谁负责？")
        ]
        assert manual.id not in {row.id for row in actions}
        assert manual.id in {row.id for row in saved.actions}

        with pytest.raises(AppError) as readonly:
            OutcomeService(session).update_action(
                actions[0].id,
                ActionEdit(expected_version=actions[0].version, content="Rewrite"),
                admin,
            )
        assert readonly.value.code == "derived_outcome_read_only"
        with pytest.raises(AppError, match="derived_outcome_read_only"):
            OutcomeService(session).update_decision(
                decisions[0].id,
                DecisionEdit(expected_version=decisions[0].version, title="Rewrite"),
                admin,
            )
        with pytest.raises(AppError, match="derived_outcome_read_only"):
            OutcomeService(session).update_question(
                questions[0].id,
                QuestionEdit(
                    expected_version=questions[0].version,
                    question_markdown="Rewrite",
                ),
                admin,
            )


def test_removing_a_tag_deletes_only_its_derived_outcome(client, agenda_context):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        agenda_service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        agenda = add_item(agenda_service, meeting, admin, "Follow-up")
        manual = OutcomeService(session).create_action(
            meeting.project_id,
            ActionWrite(
                project_id=meeting.project_id,
                meeting_id=meeting.id,
                agenda_item_id=agenda.id,
                content="Keep manual action",
            ),
            admin,
        )
        first = agenda_service.update(
            agenda.id,
            AgendaEdit(
                expected_version=agenda.version,
                notes_markdown="@行动: Derived action\n@决策: Derived decision",
            ),
            admin,
        )
        derived_action = session.scalar(
            select(ActionItem).where(
                ActionItem.source_agenda_item_id == agenda.id,
                ActionItem.source_tag_key == "action:0",
            )
        )

        agenda_service.update(
            agenda.id,
            AgendaEdit(
                expected_version=first.version,
                notes_markdown="@决策: Updated decision",
            ),
            admin,
        )

        assert session.get(ActionItem, derived_action.id) is None
        assert session.get(ActionItem, manual.id) is not None
        decision = session.scalar(
            select(Decision).where(Decision.source_agenda_item_id == agenda.id)
        )
        assert decision.decision_markdown == "Updated decision"


def test_empty_agenda_outcome_tag_is_rejected_without_saving(client, agenda_context):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        agenda_service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        agenda = add_item(agenda_service, meeting, admin, "Invalid tag")

        with pytest.raises(AppError) as error:
            agenda_service.update(
                agenda.id,
                AgendaEdit(expected_version=agenda.version, notes_markdown="@行动:   "),
                admin,
            )

        assert error.value.code == "invalid_agenda_outcome_tag"
        assert session.get(AgendaItem, agenda.id).notes_markdown == ""


def test_move_preserves_item_and_outcomes_and_repairs_both_queues(
    client, agenda_context
):
    admin, _, source_meeting_id = agenda_context
    with client.app.state.database.session() as session:
        meetings = MeetingService(session)
        source = session.get(Meeting, source_meeting_id)
        target = meetings.create_meeting(
            source.project_id,
            MeetingWrite(
                title="Target meeting",
                scheduled_start=START + timedelta(days=1),
                scheduled_end=START + timedelta(days=1, hours=1),
            ),
            admin,
        )
        service = AgendaService(session)
        before = add_item(service, source, admin, "Before")
        session.refresh(source)
        moved = add_item(service, source, admin, "Move me")
        session.refresh(source)
        after = add_item(service, source, admin, "After")
        target_tail = add_item(service, target, admin, "Target tail")
        session.refresh(source)
        session.refresh(target)

        outcomes = [
            Decision(
                project_id=source.project_id,
                meeting_id=source.id,
                agenda_item_id=moved.id,
                title="Decision",
                decision_markdown="Keep source",
                created_by=admin.id,
            ),
            ActionItem(
                project_id=source.project_id,
                meeting_id=source.id,
                agenda_item_id=moved.id,
                content="Do it",
                created_by=admin.id,
            ),
            OpenQuestion(
                project_id=source.project_id,
                meeting_id=source.id,
                agenda_item_id=moved.id,
                question_markdown="Why?",
                created_by=admin.id,
            ),
        ]
        session.add_all(outcomes)
        session.commit()
        source_version = source.version
        target_version = target.version

        result = service.move(
            moved.id,
            AgendaMove(
                target_meeting_id=target.id,
                position=0,
                expected_version=moved.version,
                expected_source_meeting_version=source_version,
                expected_target_meeting_version=target_version,
            ),
            admin,
        )

        assert result.id == moved.id
        assert result.meeting_id == target.id
        assert result.position == 0
        assert result.status.value == "planned"
        assert result.started_at is None
        assert result.completed_at is None
        assert [row.id for row in service.list(source.id)] == [before.id, after.id]
        assert [row.position for row in service.list(source.id)] == [0, 1]
        assert [row.id for row in service.list(target.id)] == [moved.id, target_tail.id]
        assert [row.position for row in service.list(target.id)] == [0, 1]
        assert result.version == 2
        assert session.get(Meeting, source.id).version == source_version + 1
        assert session.get(Meeting, target.id).version == target_version + 1
        for outcome in outcomes:
            session.refresh(outcome)
            assert outcome.project_id == source.project_id
            assert outcome.meeting_id == target.id
            assert outcome.agenda_item_id == moved.id
            assert outcome.version == 2


def _add_carried_question(session, service, source, actor, title="Carry me"):
    question = OpenQuestion(
        project_id=source.project_id,
        question_markdown=title,
        status="scheduled",
        scheduled_meeting_id=source.id,
        created_by=actor.id,
    )
    session.add(question)
    session.flush()
    item = add_item(service, source, actor, title)
    item.carry_from_open_question_id = question.id
    session.commit()
    session.refresh(source)
    session.refresh(item)
    session.refresh(question)
    return item, question


def test_move_carried_agenda_updates_question_schedule_atomically(
    client, agenda_context
):
    admin, _, source_meeting_id = agenda_context
    with client.app.state.database.session() as session:
        source = session.get(Meeting, source_meeting_id)
        future_start = datetime.now(timezone.utc) + timedelta(days=2)
        target = MeetingService(session).create_meeting(
            source.project_id,
            MeetingWrite(
                title="Carry target",
                scheduled_start=future_start,
                scheduled_end=future_start + timedelta(hours=1),
            ),
            admin,
        )
        service = AgendaService(session)
        item, question = _add_carried_question(session, service, source, admin)

        moved = service.move(
            item.id,
            AgendaMove(
                target_meeting_id=target.id,
                expected_version=item.version,
                expected_source_meeting_version=source.version,
                expected_target_meeting_version=target.version,
            ),
            admin,
        )

        session.refresh(question)
        assert moved.meeting_id == target.id
        assert question.scheduled_meeting_id == target.id
        assert question.version == 2


def test_move_carried_agenda_stale_question_rolls_back_whole_move(
    client, agenda_context, monkeypatch
):
    admin, _, source_meeting_id = agenda_context
    database = client.app.state.database
    with database.session() as session:
        source = session.get(Meeting, source_meeting_id)
        future_start = datetime.now(timezone.utc) + timedelta(days=2)
        target = MeetingService(session).create_meeting(
            source.project_id,
            MeetingWrite(
                title="Concurrent carry target",
                scheduled_start=future_start,
                scheduled_end=future_start + timedelta(hours=1),
            ),
            admin,
        )
        service = AgendaService(session)
        item, question = _add_carried_question(session, service, source, admin)

        def fail_stale():
            raise StaleDataError("concurrent carried-question update")

        monkeypatch.setattr(session, "commit", fail_stale)
        with pytest.raises(AppError) as error:
            service.move(
                item.id,
                AgendaMove(
                    target_meeting_id=target.id,
                    expected_version=item.version,
                    expected_source_meeting_version=source.version,
                    expected_target_meeting_version=target.version,
                ),
                admin,
            )

        assert error.value.code == "version_conflict"
        assert session.get(AgendaItem, item.id).meeting_id == source.id
        persisted_question = session.get(OpenQuestion, question.id)
        assert persisted_question.scheduled_meeting_id == source.id
        assert persisted_question.version == 1


@pytest.mark.parametrize("stale_side", ["source", "target"])
def test_move_rejects_stale_meeting_version_without_partial_changes(
    client, agenda_context, stale_side
):
    admin, _, source_meeting_id = agenda_context
    with client.app.state.database.session() as session:
        source = session.get(Meeting, source_meeting_id)
        target = MeetingService(session).create_meeting(
            source.project_id,
            MeetingWrite(
                title="Move target",
                scheduled_start=START + timedelta(days=1),
                scheduled_end=START + timedelta(days=1, hours=1),
            ),
            admin,
        )
        service = AgendaService(session)
        moved = add_item(service, source, admin, "Move")
        target_item = add_item(service, target, admin, "Target")
        session.refresh(source)
        session.refresh(target)
        expected_source = source.version - (1 if stale_side == "source" else 0)
        expected_target = target.version - (1 if stale_side == "target" else 0)

        with pytest.raises(AppError) as error:
            service.move(
                moved.id,
                AgendaMove(
                    target_meeting_id=target.id,
                    position=0,
                    expected_version=moved.version,
                    expected_source_meeting_version=expected_source,
                    expected_target_meeting_version=expected_target,
                ),
                admin,
            )
        assert error.value.code == "version_conflict"
        assert moved.meeting_id == source.id
        assert [row.id for row in service.list(source.id)] == [moved.id]
        assert [row.id for row in service.list(target.id)] == [target_item.id]


def test_item_and_meeting_optimistic_conflicts(client, agenda_context):
    admin, _, meeting_id = agenda_context
    database = client.app.state.database
    with database.session() as session:
        meeting = session.get(Meeting, meeting_id)
        item = add_item(AgendaService(session), meeting, admin, "Concurrent")
        item_id = item.id

    with database.session() as first_session, database.session() as second_session:
        first = AgendaService(first_session)
        second = AgendaService(second_session)
        first_item = first.get(item_id)
        second_item = second.get(item_id)
        first.update(
            item_id,
            AgendaEdit(expected_version=first_item.version, title="Winner"),
            admin,
        )
        with pytest.raises(AppError) as error:
            second.update(
                item_id,
                AgendaEdit(expected_version=second_item.version, title="Stale"),
                admin,
            )
        assert error.value.code == "version_conflict"

    with database.session() as first_session, database.session() as second_session:
        first = AgendaService(first_session)
        second = AgendaService(second_session)
        first_meeting = first_session.get(Meeting, meeting_id)
        second_meeting = second_session.get(Meeting, meeting_id)
        first.create(
            meeting_id,
            AgendaWrite(title="Winner append", agenda_type="discussion"),
            admin,
            expected_meeting_version=first_meeting.version,
        )
        with pytest.raises(AppError) as error:
            second.create(
                meeting_id,
                AgendaWrite(title="Stale append", agenda_type="discussion"),
                admin,
                expected_meeting_version=second_meeting.version,
            )
        assert error.value.code == "version_conflict"
