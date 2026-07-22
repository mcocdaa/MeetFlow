from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.meetings.models import (
    Meeting,
    MeetingSeries,
)
from app.meetings.schemas import (
    MeetingEdit,
    MeetingSeriesEdit,
    MeetingSeriesWrite,
    MeetingWrite,
    OccurrenceWrite,
)
from app.meetings.service import MeetingService
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService

START = datetime(2026, 7, 21, 9, tzinfo=timezone.utc)


@pytest.fixture
def meeting_users(client):
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        member = User(
            username="meeting-member",
            display_name="Meeting Member",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        recorder = User(
            username="meeting-recorder",
            display_name="Meeting Recorder",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add_all([member, recorder])
        session.commit()
        for user in (admin, member, recorder):
            session.refresh(user)
        yield admin, member, recorder


@pytest.fixture
def project(client, meeting_users):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        project = ProjectService(session).create(
            ProjectWrite(
                name="Meeting domain",
                slug="meeting-domain",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id, member.id, recorder.id],
            ),
            admin,
        )
        session.expunge(project)
        return project


def series_payload(admin, member, recorder, **overrides):
    values = {
        "title": "Weekly delivery review",
        "purpose_markdown": "  # Keep exact markdown  \n",
        "recurrence_description": "  Every Tuesday  ",
        "default_duration_minutes": 45,
        "default_host_user_id": admin.id,
        "default_recorder_user_id": recorder.id,
        "participants": [
            {"user_id": member.id, "participation_role": "attendee"},
            {"user_id": admin.id, "participation_role": "host"},
            {"user_id": member.id, "participation_role": "presenter"},
        ],
        "standing_items": [
            {
                "title": "Metrics",
                "agenda_type": "information",
                "default_owner_user_id": member.id,
                "default_duration_minutes": 10,
            },
            {
                "title": "Risks",
                "agenda_type": "discussion",
                "default_duration_minutes": 15,
            },
        ],
    }
    values.update(overrides)
    return MeetingSeriesWrite(**values)


def test_occurrence_copies_current_series_defaults_and_participants(
    client, project, meeting_users
):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        series = service.create_series(
            project.id, series_payload(admin, member, recorder), admin
        )
        occurrence = service.create_occurrence(
            series.id,
            OccurrenceWrite(
                title="Delivery review · 21 July",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=45),
            ),
            admin,
        )

        assert occurrence.project_id == project.id
        assert occurrence.series_id == series.id
        assert occurrence.purpose_markdown == "  # Keep exact markdown  \n"
        assert occurrence.host_user_id == admin.id
        assert occurrence.recorder_user_id == recorder.id
        # First appearance wins, including role and position.
        assert [
            (row.user_id, row.participation_role.value)
            for row in occurrence.participants
        ] == [
            (member.id, "attendee"),
            (admin.id, "host"),
        ]


def test_later_series_edits_never_rewrite_existing_occurrence(
    client, project, meeting_users
):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        series = service.create_series(
            project.id, series_payload(admin, member, recorder), admin
        )
        occurrence = service.create_occurrence(
            series.id,
            OccurrenceWrite(
                title="Original occurrence",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=45),
            ),
            admin,
        )
        service.update_series(
            series.id,
            MeetingSeriesEdit(
                expected_version=1,
                purpose_markdown="Changed series purpose",
                default_host_user_id=member.id,
                participants=[
                    {"user_id": recorder.id, "participation_role": "recorder"}
                ],
                standing_items=[
                    {
                        "title": "Replacement item",
                        "agenda_type": "decision",
                        "default_owner_user_id": recorder.id,
                    }
                ],
            ),
            admin,
        )
        session.refresh(occurrence)

        assert occurrence.purpose_markdown == "  # Keep exact markdown  \n"
        assert occurrence.host_user_id == admin.id
        assert [row.user_id for row in occurrence.participants] == [member.id, admin.id]
        assert [row.title for row in occurrence.agenda_items] == ["Metrics", "Risks"]


def test_standing_items_are_ordered_serialized_and_copied_to_occurrence(
    client, project, meeting_users
):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        series = service.create_series(
            project.id, series_payload(admin, member, recorder), admin
        )
        body = service.serialize_series(series)

        assert [item["title"] for item in body["standing_items"]] == [
            "Metrics",
            "Risks",
        ]
        assert body["standing_items"][0]["default_owner"]["id"] == member.id
        occurrence = service.create_occurrence(
            series.id,
            OccurrenceWrite(
                title="Agenda copy",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=45),
            ),
            admin,
        )
        assert [item.title for item in occurrence.agenda_items] == [
            "Metrics",
            "Risks",
        ]
        assert occurrence.agenda_items[0].presenter_user_id == member.id
        assert occurrence.agenda_items[0].proposer_user_id is None
        assert occurrence.agenda_items[0].notes_markdown == ""


def test_series_atomic_two_session_conflict(client, project, meeting_users):
    admin, member, recorder = meeting_users
    database = client.app.state.database
    with database.session() as seed:
        series = MeetingService(seed).create_series(
            project.id, series_payload(admin, member, recorder), admin
        )
        series_id = series.id

    with database.session() as first, database.session() as second:
        assert first.get(MeetingSeries, series_id).version == 1
        assert second.get(MeetingSeries, series_id).version == 1
        MeetingService(first).update_series(
            series_id, MeetingSeriesEdit(expected_version=1, title="First"), admin
        )
        with pytest.raises(AppError) as error:
            MeetingService(second).update_series(
                series_id, MeetingSeriesEdit(expected_version=1, title="Second"), admin
            )
        assert error.value.code == "version_conflict"
        assert error.value.details == {"expected_version": 1, "actual_version": 2}


def test_meeting_atomic_two_session_conflict(client, project, meeting_users):
    admin, _, _ = meeting_users
    database = client.app.state.database
    with database.session() as seed:
        meeting = MeetingService(seed).create_meeting(
            project.id,
            MeetingWrite(
                title="Concurrent",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=30),
            ),
            admin,
        )
        meeting_id = meeting.id

    with database.session() as first, database.session() as second:
        assert first.get(Meeting, meeting_id).version == 1
        assert second.get(Meeting, meeting_id).version == 1
        MeetingService(first).update_meeting(
            meeting_id, MeetingEdit(expected_version=1, title="First"), admin
        )
        with pytest.raises(AppError) as error:
            MeetingService(second).update_meeting(
                meeting_id, MeetingEdit(expected_version=1, title="Second"), admin
            )
        assert error.value.details == {"expected_version": 1, "actual_version": 2}


def test_routes_create_and_serialize_series_and_occurrence(
    authenticated_client, project, meeting_users
):
    admin, member, recorder = meeting_users
    created = authenticated_client.post(
        f"/api/projects/{project.id}/meeting-series",
        json=series_payload(admin, member, recorder).model_dump(mode="json"),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["project"]["id"] == project.id
    assert body["participants"][0]["user"]["id"] == member.id
    assert body["standing_items"][0]["position"] == 0

    occurrence = authenticated_client.post(
        f"/api/meeting-series/{body['id']}/occurrences",
        json={
            "title": "Routed occurrence",
            "scheduled_start": START.isoformat(),
            "scheduled_end": (START + timedelta(minutes=45)).isoformat(),
        },
    )
    assert occurrence.status_code == 201
    assert occurrence.json()["series"]["id"] == body["id"]
    detail = authenticated_client.get(f"/api/meetings/{occurrence.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["version"] == 1
