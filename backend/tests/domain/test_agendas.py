from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agendas.models import AgendaItem
from app.agendas.schemas import (
    AgendaCommand,
    AgendaEdit,
    AgendaReorder,
    AgendaWrite,
)
from app.agendas.service import AgendaService
from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.meetings.models import Meeting
from app.meetings.schemas import MeetingWrite
from app.meetings.service import MeetingService
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
        AgendaWrite(title=title, position=position, **values),
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
        assert skipped.status.value == "skipped"
        assert skipped.completed_at is not None
        assert canceled.status.value == "canceled"
        assert canceled.completed_at is not None

        with pytest.raises(AppError) as error:
            service.skip(completed.id, AgendaCommand(expected_version=2), admin)
        assert error.value.code == "invalid_agenda_transition"


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
                AgendaWrite(title="Too late"),
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
            AgendaWrite(title="Winner append"),
            admin,
            expected_meeting_version=first_meeting.version,
        )
        with pytest.raises(AppError) as error:
            second.create(
                meeting_id,
                AgendaWrite(title="Stale append"),
                admin,
                expected_meeting_version=second_meeting.version,
            )
        assert error.value.code == "version_conflict"


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
            json={"title": "No auth"},
        )
    assert response.status_code == 401
