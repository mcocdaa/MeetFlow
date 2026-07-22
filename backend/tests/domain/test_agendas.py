from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, select
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
from app.meetings.schemas import MeetingWrite
from app.meetings.service import MeetingService
from app.outcomes.models import ActionItem, Decision, OpenQuestion
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


def test_exact_reorder_rejects_invalid_sets_without_partial_changes(
    client, agenda_context
):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        first = add_item(service, meeting, admin, "First")
        session.refresh(meeting)
        second = add_item(service, meeting, admin, "Second")
        session.refresh(meeting)
        third = add_item(service, meeting, admin, "Third")
        session.refresh(meeting)

        for invalid in (
            [first.id, second.id],
            [first.id, first.id, third.id],
            [first.id, second.id, "foreign-id"],
        ):
            with pytest.raises(AppError) as error:
                service.reorder(
                    meeting_id,
                    AgendaReorder(
                        ids=invalid, expected_meeting_version=meeting.version
                    ),
                    admin,
                )
            assert error.value.code == "invalid_agenda_set"
            assert [item.id for item in service.list(meeting_id)] == [
                first.id,
                second.id,
                third.id,
            ]

        reordered = service.reorder(
            meeting_id,
            AgendaReorder(
                ids=[third.id, first.id, second.id],
                expected_meeting_version=meeting.version,
            ),
            admin,
        )
        assert [item.id for item in reordered] == [third.id, first.id, second.id]
        assert [item.position for item in reordered] == [0, 1, 2]


def test_update_preserves_markdown_and_validates_user(client, agenda_context):
    admin, presenter, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        item = add_item(service, meeting, admin, "Topic")

        edited = service.update(
            item.id,
            AgendaEdit(
                expected_version=1,
                title="  Renamed  ",
                notes_markdown="  # exact markdown  \n",
                presenter_user_id=presenter.id,
            ),
            admin,
        )
        assert edited.title == "Renamed"
        assert edited.notes_markdown == "  # exact markdown  \n"
        assert edited.presenter_user_id == presenter.id

        with pytest.raises(AppError) as error:
            service.update(
                item.id,
                AgendaEdit(expected_version=2, proposer_user_id="missing"),
                admin,
            )
        assert error.value.code == "user_not_found"


def test_schema_requires_type_rejects_blank_refs_and_allows_explicit_clear():
    with pytest.raises(ValidationError):
        AgendaWrite(title="Missing type")
    with pytest.raises(ValidationError):
        AgendaWrite(
            title="Too long",
            agenda_type="discussion",
            estimated_minutes=481,
        )
    with pytest.raises(ValidationError):
        AgendaEdit(expected_version=1, estimated_minutes=481)
    for field in (
        "proposer_user_id",
        "presenter_user_id",
    ):
        with pytest.raises(ValidationError):
            AgendaEdit(expected_version=1, **{field: "   "})
        assert (
            AgendaEdit(expected_version=1, **{field: None}).model_dump(
                exclude_unset=True
            )[field]
            is None
        )


def test_edit_can_clear_optional_user_refs_without_poisoning_session(
    client, agenda_context
):
    admin, presenter, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        item = add_item(
            service,
            meeting,
            admin,
            "Clear refs",
            proposer_user_id=presenter.id,
            presenter_user_id=presenter.id,
        )
        cleared = service.update(
            item.id,
            AgendaEdit(
                expected_version=1,
                proposer_user_id=None,
                presenter_user_id=None,
            ),
            admin,
        )
        assert cleared.proposer_user_id is None
        assert cleared.presenter_user_id is None
        assert session.scalar(select(AgendaItem.id).where(AgendaItem.id == item.id))


def test_public_agenda_schemas_forbid_internal_provenance_fields():
    with pytest.raises(ValidationError):
        AgendaWrite(
            title="Internal carry",
            agenda_type="discussion",
            carry_from_open_question_id="question-id",
        )
    with pytest.raises(ValidationError):
        AgendaEdit(
            expected_version=1,
            carry_from_open_question_id="question-id",
        )


def test_commands_set_status_timestamps_and_reject_invalid_transition(
    client, agenda_context
):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        completed = add_item(service, meeting, admin, "Complete")
        session.refresh(meeting)
        skipped = add_item(service, meeting, admin, "Skip")
        session.refresh(meeting)
        canceled = add_item(service, meeting, admin, "Cancel")

        completed = service.complete(
            completed.id, AgendaCommand(expected_version=1), admin
        )
        skipped = service.skip(skipped.id, AgendaCommand(expected_version=1), admin)
        canceled = service.cancel(canceled.id, AgendaCommand(expected_version=1), admin)
        assert completed.status.value == "completed"
        assert completed.completed_at is not None
        assert completed.started_at is not None
        assert skipped.status.value == "skipped"
        assert skipped.completed_at is not None
        assert skipped.started_at is None
        assert canceled.status.value == "canceled"
        assert canceled.completed_at is not None
        assert canceled.started_at is None

        with pytest.raises(AppError) as error:
            service.skip(completed.id, AgendaCommand(expected_version=2), admin)
        assert error.value.code == "invalid_agenda_transition"


def test_start_requires_active_meeting_and_only_transitions_planned_item(
    client, agenda_context
):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        item = add_item(service, meeting, admin, "Current topic")

        with pytest.raises(AppError) as error:
            service.start(item.id, AgendaCommand(expected_version=item.version), admin)
        assert error.value.code == "meeting_not_in_progress"

        meeting.status = "in_progress"
        meeting.version += 1
        session.commit()
        started = service.start(
            item.id, AgendaCommand(expected_version=item.version), admin
        )
        assert started.status.value == "in_progress"
        assert started.started_at is not None
        assert started.completed_at is None
        assert started.version == 2

        with pytest.raises(AppError) as error:
            service.start(
                item.id, AgendaCommand(expected_version=started.version), admin
            )
        assert error.value.code == "invalid_agenda_transition"


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


def test_move_carried_agenda_rejects_past_target_and_inconsistent_question(
    client, agenda_context
):
    admin, _, source_meeting_id = agenda_context
    with client.app.state.database.session() as session:
        source = session.get(Meeting, source_meeting_id)
        past_start = datetime.now(timezone.utc) - timedelta(days=1)
        past = MeetingService(session).create_meeting(
            source.project_id,
            MeetingWrite(
                title="Past carry target",
                scheduled_start=past_start,
                scheduled_end=past_start + timedelta(hours=1),
            ),
            admin,
        )
        service = AgendaService(session)
        item, question = _add_carried_question(session, service, source, admin)

        with pytest.raises(AppError) as past_error:
            service.move(
                item.id,
                AgendaMove(
                    target_meeting_id=past.id,
                    expected_version=item.version,
                    expected_source_meeting_version=source.version,
                    expected_target_meeting_version=past.version,
                ),
                admin,
            )
        assert past_error.value.code == "meeting_not_future"
        assert item.meeting_id == source.id
        assert question.scheduled_meeting_id == source.id

        future_start = datetime.now(timezone.utc) + timedelta(days=2)
        future = MeetingService(session).create_meeting(
            source.project_id,
            MeetingWrite(
                title="Future carry target",
                scheduled_start=future_start,
                scheduled_end=future_start + timedelta(hours=1),
            ),
            admin,
        )
        question.scheduled_meeting_id = future.id
        session.commit()
        session.refresh(source)
        session.refresh(future)
        with pytest.raises(AppError) as inconsistent:
            service.move(
                item.id,
                AgendaMove(
                    target_meeting_id=future.id,
                    expected_version=item.version,
                    expected_source_meeting_version=source.version,
                    expected_target_meeting_version=future.version,
                ),
                admin,
            )
        assert inconsistent.value.code == "source_mismatch"
        assert item.meeting_id == source.id


def test_move_clamps_position_and_rejects_same_or_cross_project_or_locked_target(
    client, agenda_context
):
    admin, _, source_meeting_id = agenda_context
    with client.app.state.database.session() as session:
        source = session.get(Meeting, source_meeting_id)
        meetings = MeetingService(session)
        target = meetings.create_meeting(
            source.project_id,
            MeetingWrite(
                title="Editable target",
                scheduled_start=START + timedelta(days=1),
                scheduled_end=START + timedelta(days=1, hours=1),
            ),
            admin,
        )
        service = AgendaService(session)
        moved = add_item(service, source, admin, "Move")
        target_first = add_item(service, target, admin, "Target first")
        session.refresh(source)
        session.refresh(target)

        with pytest.raises(AppError) as error:
            service.move(
                moved.id,
                AgendaMove(
                    target_meeting_id=source.id,
                    expected_version=moved.version,
                    expected_source_meeting_version=source.version,
                    expected_target_meeting_version=source.version,
                ),
                admin,
            )
        assert error.value.code == "source_mismatch"

        other_project = ProjectService(session).create(
            ProjectWrite(
                name="Other",
                slug="agenda-other",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id],
            ),
            admin,
        )
        cross_project = meetings.create_meeting(
            other_project.id,
            MeetingWrite(
                title="Wrong project",
                scheduled_start=START + timedelta(days=2),
                scheduled_end=START + timedelta(days=2, hours=1),
            ),
            admin,
        )
        with pytest.raises(AppError) as error:
            service.move(
                moved.id,
                AgendaMove(
                    target_meeting_id=cross_project.id,
                    expected_version=moved.version,
                    expected_source_meeting_version=source.version,
                    expected_target_meeting_version=cross_project.version,
                ),
                admin,
            )
        assert error.value.code == "source_mismatch"

        target.status = "completed"
        session.commit()
        with pytest.raises(AppError) as error:
            service.move(
                moved.id,
                AgendaMove(
                    target_meeting_id=target.id,
                    position=500,
                    expected_version=moved.version,
                    expected_source_meeting_version=source.version,
                    expected_target_meeting_version=target.version,
                ),
                admin,
            )
        assert error.value.code == "meeting_completed"

        target.status = "draft"
        session.commit()
        session.refresh(source)
        session.refresh(target)
        moved = service.move(
            moved.id,
            AgendaMove(
                target_meeting_id=target.id,
                position=500,
                expected_version=moved.version,
                expected_source_meeting_version=source.version,
                expected_target_meeting_version=target.version,
            ),
            admin,
        )
        assert moved.position == 1
        assert [row.id for row in service.list(target.id)] == [
            target_first.id,
            moved.id,
        ]


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


def test_complete_preserves_existing_started_at(client, agenda_context):
    admin, _, meeting_id = agenda_context
    started = datetime(2026, 7, 22, 9, 15, tzinfo=timezone.utc)
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        item = add_item(service, meeting, admin, "Already underway")
        item.status = "in_progress"
        item.started_at = started
        session.commit()

        completed = service.complete(
            item.id, AgendaCommand(expected_version=item.version), admin
        )
        actual_started = completed.started_at
        if actual_started.tzinfo is None:
            actual_started = actual_started.replace(tzinfo=timezone.utc)
        assert actual_started == started


@pytest.mark.parametrize(
    "operation", ["create", "update", "reorder", "transition", "delete"]
)
def test_canceled_meeting_rejects_every_agenda_write(client, agenda_context, operation):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        item = add_item(service, meeting, admin, "Frozen")
        session.refresh(meeting)
        meeting.status = "canceled"
        session.commit()

        with pytest.raises(AppError) as error:
            if operation == "create":
                service.create(
                    meeting_id,
                    AgendaWrite(title="New", agenda_type="discussion"),
                    admin,
                    expected_meeting_version=meeting.version,
                )
            elif operation == "update":
                service.update(
                    item.id,
                    AgendaEdit(expected_version=item.version, title="Changed"),
                    admin,
                )
            elif operation == "reorder":
                service.reorder(
                    meeting_id,
                    AgendaReorder(
                        ids=[item.id], expected_meeting_version=meeting.version
                    ),
                    admin,
                )
            elif operation == "transition":
                service.complete(
                    item.id, AgendaCommand(expected_version=item.version), admin
                )
            else:
                service.delete(
                    item.id,
                    AgendaCommand(expected_version=item.version),
                    admin,
                    expected_meeting_version=meeting.version,
                )
        assert error.value.code == "meeting_immutable"


@pytest.mark.parametrize("operation", ["edit", "transition"])
def test_parent_lifecycle_race_rejects_stale_item_write(
    client, agenda_context, operation
):
    admin, _, meeting_id = agenda_context
    database = client.app.state.database
    with database.session() as seed:
        meeting = seed.get(Meeting, meeting_id)
        item = add_item(AgendaService(seed), meeting, admin, "Original")
        item_id = item.id

    with database.session() as stale_session, database.session() as winner_session:
        stale_service = AgendaService(stale_session)
        stale_item = stale_service.get(item_id)
        stale_item.meeting.version
        winner = winner_session.get(Meeting, meeting_id)
        winner.status = "completed"
        winner.version += 1
        winner.updated_by = admin.id
        winner_session.commit()

        with pytest.raises(AppError) as error:
            if operation == "edit":
                stale_service.update(
                    item_id,
                    AgendaEdit(expected_version=stale_item.version, title="Lost edit"),
                    admin,
                )
            else:
                stale_service.complete(
                    item_id,
                    AgendaCommand(expected_version=stale_item.version),
                    admin,
                )
        assert error.value.code == "meeting_completed"
        assert stale_session.scalar(select(Meeting.id).where(Meeting.id == meeting_id))

    with database.session() as verify:
        unchanged = verify.get(AgendaItem, item_id)
        assert unchanged.title == "Original"
        assert unchanged.status.value == "planned"
        assert unchanged.version == 1


def test_completed_meeting_is_immutable_and_empty_item_can_be_deleted(
    client, agenda_context
):
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        item = add_item(service, meeting, admin, "Temporary")
        session.refresh(meeting)
        service.delete(
            item.id,
            AgendaCommand(expected_version=1),
            admin,
            expected_meeting_version=meeting.version,
        )
        assert session.get(AgendaItem, item.id) is None

        meeting.status = "completed"
        session.commit()
        with pytest.raises(AppError) as error:
            service.create(
                meeting.id,
                AgendaWrite(title="Too late", agenda_type="discussion"),
                admin,
                expected_meeting_version=meeting.version,
            )
        assert error.value.code == "meeting_completed"


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


def test_stale_reorder_reports_version_before_changed_id_set(client, agenda_context):
    admin, _, meeting_id = agenda_context
    database = client.app.state.database
    with database.session() as seed:
        meeting = seed.get(Meeting, meeting_id)
        original = add_item(AgendaService(seed), meeting, admin, "Original")
        original_id = original.id

    with database.session() as stale_session, database.session() as winner_session:
        stale_meeting = stale_session.get(Meeting, meeting_id)
        expected = stale_meeting.version
        winner_meeting = winner_session.get(Meeting, meeting_id)
        add_item(AgendaService(winner_session), winner_meeting, admin, "New item")

        with pytest.raises(AppError) as error:
            AgendaService(stale_session).reorder(
                meeting_id,
                AgendaReorder(ids=[original_id], expected_meeting_version=expected),
                admin,
            )
        assert error.value.code == "version_conflict"
        assert error.value.details == {
            "expected_version": expected,
            "actual_version": expected + 1,
        }
        assert stale_session.scalar(select(Meeting.id).where(Meeting.id == meeting_id))


def test_agenda_routes_require_auth_and_serialize(authenticated_client, agenda_context):
    admin, _, meeting_id = agenda_context
    client = authenticated_client
    with client.app.state.database.session() as session:
        version = session.get(Meeting, meeting_id).version

    response = client.post(
        f"/api/meetings/{meeting_id}/agenda-items",
        params={"expected_meeting_version": version},
        json={"title": "API topic", "agenda_type": "decision"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "API topic"
    assert body["agenda_type"] == "decision"
    assert body["status"] == "planned"
    assert body["created_by"]["id"] == admin.id

    unauthenticated = client.__class__(client.app)
    with unauthenticated:
        response = unauthenticated.post(
            f"/api/meetings/{meeting_id}/agenda-items",
            params={"expected_meeting_version": version + 1},
            json={"title": "No auth", "agenda_type": "discussion"},
        )
    assert response.status_code == 401


def test_start_and_move_routes_require_auth_and_return_updated_agenda(
    authenticated_client, agenda_context
):
    client = authenticated_client
    admin, _, source_meeting_id = agenda_context
    with client.app.state.database.session() as session:
        source = session.get(Meeting, source_meeting_id)
        target = MeetingService(session).create_meeting(
            source.project_id,
            MeetingWrite(
                title="API target",
                scheduled_start=START + timedelta(days=1),
                scheduled_end=START + timedelta(days=1, hours=1),
            ),
            admin,
        )
        item = add_item(AgendaService(session), source, admin, "API flow")
        source.status = "in_progress"
        source.version += 1
        session.commit()
        item_id = item.id
        target_id = target.id
        item_version = item.version

    response = client.post(
        f"/api/agenda-items/{item_id}/start",
        json={"expected_version": item_version},
    )
    assert response.status_code == 200
    started = response.json()
    assert started["status"] == "in_progress"
    assert started["started_at"] is not None

    with client.app.state.database.session() as session:
        source_version = session.get(Meeting, source_meeting_id).version
        target_version = session.get(Meeting, target_id).version

    response = client.post(
        f"/api/agenda-items/{item_id}/move",
        json={
            "target_meeting_id": target_id,
            "position": 0,
            "expected_version": started["version"],
            "expected_source_meeting_version": source_version,
            "expected_target_meeting_version": target_version,
        },
    )
    assert response.status_code == 200
    moved = response.json()
    assert moved["meeting_id"] == target_id
    assert moved["status"] == "planned"

    unauthenticated = TestClient(client.app)
    with unauthenticated:
        for path, body in (
            (
                f"/api/agenda-items/{item_id}/start",
                {"expected_version": moved["version"]},
            ),
            (
                f"/api/agenda-items/{item_id}/move",
                {
                    "target_meeting_id": source_meeting_id,
                    "expected_version": moved["version"],
                    "expected_source_meeting_version": target_version + 1,
                    "expected_target_meeting_version": source_version + 1,
                },
            ),
        ):
            assert unauthenticated.post(path, json=body).status_code == 401


def test_all_agenda_mutation_routes_have_auth_and_expected_status_codes(
    authenticated_client, agenda_context
):
    client = authenticated_client
    _, _, meeting_id = agenda_context

    def meeting_version():
        with client.app.state.database.session() as session:
            return session.get(Meeting, meeting_id).version

    def create(title):
        response = client.post(
            f"/api/meetings/{meeting_id}/agenda-items",
            params={"expected_meeting_version": meeting_version()},
            json={"title": title, "agenda_type": "discussion"},
        )
        assert response.status_code == 201
        return response.json()

    edited = create("Edit")
    completed = create("Complete")
    skipped = create("Skip")
    canceled = create("Cancel")
    deleted = create("Delete")

    response = client.put(
        f"/api/agenda-items/{edited['id']}",
        json={
            "expected_version": edited["version"],
            "presenter_user_id": "   ",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    response = client.put(
        f"/api/agenda-items/{edited['id']}",
        json={"expected_version": edited["version"], "title": "Edited"},
    )
    assert response.status_code == 200
    response = client.post(
        f"/api/agenda-items/{completed['id']}/complete",
        json={"expected_version": completed["version"]},
    )
    assert response.status_code == 200
    response = client.post(
        f"/api/agenda-items/{skipped['id']}/skip",
        json={"expected_version": skipped["version"]},
    )
    assert response.status_code == 200
    response = client.post(
        f"/api/agenda-items/{canceled['id']}/cancel",
        json={"expected_version": canceled["version"]},
    )
    assert response.status_code == 200

    ids = [canceled["id"], skipped["id"], completed["id"], edited["id"], deleted["id"]]
    response = client.post(
        f"/api/meetings/{meeting_id}/agenda-items/reorder",
        json={"ids": ids, "expected_meeting_version": meeting_version()},
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ids

    delete_version = next(
        item["version"] for item in response.json() if item["id"] == deleted["id"]
    )
    response = client.request(
        "DELETE",
        f"/api/agenda-items/{deleted['id']}",
        params={"expected_meeting_version": meeting_version()},
        json={"expected_version": delete_version},
    )
    assert response.status_code == 204

    unauthenticated = TestClient(client.app)
    with unauthenticated:
        requests = [
            (
                "PUT",
                f"/api/agenda-items/{edited['id']}",
                {},
                {"expected_version": 2, "title": "x"},
            ),
            (
                "DELETE",
                f"/api/agenda-items/{edited['id']}",
                {"expected_meeting_version": meeting_version()},
                {"expected_version": 2},
            ),
            (
                "POST",
                f"/api/meetings/{meeting_id}/agenda-items/reorder",
                {},
                {"ids": ids[:-1], "expected_meeting_version": meeting_version()},
            ),
            (
                "POST",
                f"/api/agenda-items/{edited['id']}/complete",
                {},
                {"expected_version": 2},
            ),
            (
                "POST",
                f"/api/agenda-items/{edited['id']}/skip",
                {},
                {"expected_version": 2},
            ),
            (
                "POST",
                f"/api/agenda-items/{edited['id']}/cancel",
                {},
                {"expected_version": 2},
            ),
        ]
        for method, path, params, payload in requests:
            assert (
                unauthenticated.request(
                    method, path, params=params, json=payload
                ).status_code
                == 401
            )


def test_reorder_route_serialization_has_bounded_queries(
    authenticated_client, agenda_context
):
    client = authenticated_client
    admin, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        service = AgendaService(session)
        meeting = session.get(Meeting, meeting_id)
        for index in range(8):
            add_item(service, meeting, admin, f"Topic {index}")
            session.refresh(meeting)
        ids = [item.id for item in service.list(meeting_id)]
        version = meeting.version

    selects = []

    def count_select(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    engine = client.app.state.database.engine
    event.listen(engine, "before_cursor_execute", count_select)
    try:
        response = client.post(
            f"/api/meetings/{meeting_id}/agenda-items/reorder",
            json={"ids": ids, "expected_meeting_version": version},
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_select)

    assert response.status_code == 200
    assert len(response.json()) == 8
    # Auth, meeting load, direct version check, queue load, eager response load.
    assert len(selects) <= 5
