from datetime import date, datetime, time, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.auth.models import User, UserRole, UserStatus
from app.agendas.models import AgendaItem
from app.domain.enums import OccurrenceKind
from app.errors import AppError
from app.meetings.models import (
    Meeting,
    MeetingSeries,
)
from app.meetings.schemas import (
    LifecycleCommand,
    MeetingEdit,
    MeetingSeriesEdit,
    MeetingSeriesWrite,
    MeetingWrite,
    OccurrenceWrite,
)
from app.meetings.recurrence import RecurrenceRule
from app.meetings.scheduler import MeetingSeriesScheduler
from app.meetings.service import MeetingService
from app.outcomes.models import ActionItem, Decision, OpenQuestion
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


def test_series_persists_structured_recurrence_rule(client, project, meeting_users):
    admin, member, recorder = meeting_users
    payload = MeetingSeriesWrite(
        title="Daily delivery review",
        recurrence_frequency="daily",
        recurrence_interval=1,
        recurrence_local_time=time(21, 30),
        recurrence_timezone="Asia/Shanghai",
        recurrence_anchor_date=date(2026, 7, 30),
        default_duration_minutes=45,
        default_host_user_id=admin.id,
        default_recorder_user_id=recorder.id,
        participants=[{"user_id": member.id, "participation_role": "attendee"}],
    )
    with client.app.state.database.session() as session:
        series = MeetingService(session).create_series(project.id, payload, admin)

        assert series.recurrence_frequency == "daily"
        assert series.recurrence_interval == 1
        assert series.recurrence_local_time == time(21, 30)
        assert series.recurrence_timezone == "Asia/Shanghai"
        assert series.recurrence_anchor_date == date(2026, 7, 30)
        assert MeetingService(session).serialize_series(series)["recurrence"] == {
            "frequency": "daily",
            "interval": 1,
            "weekday": None,
            "month_day": None,
            "month": None,
            "local_time": "21:30:00",
            "timezone": "Asia/Shanghai",
            "anchor_date": "2026-07-30",
        }


def test_meeting_domain_exposes_occurrence_duration_and_outcome_source_fields():
    assert "occurrence_kind" in Meeting.__table__.c
    assert "series_slot_at" in Meeting.__table__.c
    assert "actual_duration_seconds" in AgendaItem.__table__.c
    for model in (Decision, ActionItem, OpenQuestion):
        assert "source_agenda_item_id" in model.__table__.c
        assert "source_tag_key" in model.__table__.c


def test_manual_series_occurrence_serializes_its_kind(client, project, meeting_users):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        series = service.create_series(
            project.id, series_payload(admin, member, recorder), admin
        )
        meeting = service.create_occurrence(
            series.id,
            OccurrenceWrite(
                title="Temporary occurrence",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=45),
            ),
            admin,
        )

        body = service.serialize_meeting(meeting)
        assert body["occurrence_kind"] == "manual"
        assert body["series_slot_at"] is None


def test_monthly_31st_uses_the_last_day_in_february():
    rule = RecurrenceRule.monthly(
        interval=1,
        month_day=31,
        local_time=time(9),
        timezone_name="Asia/Shanghai",
        anchor_date=date(2026, 1, 31),
    )

    assert rule.slot_for(date(2026, 2, 1)) == datetime(
        2026, 2, 28, 1, tzinfo=timezone.utc
    )


def test_recurrence_slots_cover_daily_weekly_and_yearly_rules():
    daily = RecurrenceRule.daily(
        interval=2,
        local_time=time(9),
        timezone_name="UTC",
        anchor_date=date(2026, 7, 1),
    )
    weekly = RecurrenceRule.weekly(
        interval=2,
        weekday=0,
        local_time=time(9),
        timezone_name="UTC",
        anchor_date=date(2026, 7, 1),
    )
    yearly = RecurrenceRule.yearly(
        interval=1,
        month=2,
        month_day=29,
        local_time=time(9),
        timezone_name="UTC",
        anchor_date=date(2024, 2, 29),
    )

    assert daily.slots_through(datetime(2026, 7, 6, 9, tzinfo=timezone.utc)) == [
        datetime(2026, 7, 1, 9, tzinfo=timezone.utc),
        datetime(2026, 7, 3, 9, tzinfo=timezone.utc),
        datetime(2026, 7, 5, 9, tzinfo=timezone.utc),
    ]
    assert weekly.slots_through(datetime(2026, 7, 31, 9, tzinfo=timezone.utc)) == [
        datetime(2026, 7, 6, 9, tzinfo=timezone.utc),
        datetime(2026, 7, 20, 9, tzinfo=timezone.utc),
    ]
    assert yearly.slots_through(datetime(2026, 3, 1, 9, tzinfo=timezone.utc)) == [
        datetime(2024, 2, 29, 9, tzinfo=timezone.utc),
        datetime(2025, 2, 28, 9, tzinfo=timezone.utc),
        datetime(2026, 2, 28, 9, tzinfo=timezone.utc),
    ]


def test_materialize_due_occurrences_is_idempotent_and_preserves_manual_items(
    client, project, meeting_users
):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        series = service.create_series(
            project.id,
            series_payload(
                admin,
                member,
                recorder,
                recurrence_frequency="daily",
                recurrence_interval=1,
                recurrence_local_time=time(21, 30),
                recurrence_timezone="Asia/Shanghai",
                recurrence_anchor_date=date(2026, 7, 30),
            ),
            admin,
        )
        manual = service.create_occurrence(
            series.id,
            OccurrenceWrite(
                title="Temporary delivery review",
                scheduled_start=datetime(2026, 7, 30, 13, 30, tzinfo=timezone.utc),
                scheduled_end=datetime(2026, 7, 30, 14, 15, tzinfo=timezone.utc),
            ),
            admin,
        )

        first = service.materialize_due_occurrences(
            now=datetime(2026, 7, 31, tzinfo=timezone.utc)
        )
        second = service.materialize_due_occurrences(
            now=datetime(2026, 7, 31, tzinfo=timezone.utc)
        )

        assert [item.occurrence_kind for item in first] == [OccurrenceKind.scheduled]
        scheduled_body = service.serialize_meeting(first[0])
        assert scheduled_body["series_slot_at"] == datetime(
            2026, 7, 30, 13, 30, tzinfo=timezone.utc
        )
        assert scheduled_body["scheduled_start"] == scheduled_body["series_slot_at"]
        assert scheduled_body["scheduled_end"] == datetime(
            2026, 7, 30, 14, 15, tzinfo=timezone.utc
        )
        assert second == []
        assert manual.occurrence_kind == OccurrenceKind.manual
        assert manual.series_slot_at is None
        listed = service.list_meetings(project.id)
        assert {item["occurrence_kind"] for item in listed} == {"manual", "scheduled"}


def test_series_detail_reconciles_due_occurrences(
    client, project, meeting_users, monkeypatch
):
    admin, member, recorder = meeting_users
    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    monkeypatch.setattr("app.meetings.service.utcnow", lambda: now)
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        series = service.create_series(
            project.id,
            series_payload(
                admin,
                member,
                recorder,
                recurrence_frequency="daily",
                recurrence_local_time=time(21, 30),
                recurrence_timezone="Asia/Shanghai",
                recurrence_anchor_date=date(2026, 7, 30),
            ),
            admin,
        )

        service.series_detail(series.id)

        scheduled = session.scalars(
            select(Meeting).where(Meeting.series_id == series.id)
        ).all()
        assert [item.occurrence_kind for item in scheduled] == [
            OccurrenceKind.scheduled
        ]


def test_series_scheduler_materializes_due_occurrences(
    client, project, meeting_users
):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        MeetingService(session).create_series(
            project.id,
            series_payload(
                admin,
                member,
                recorder,
                recurrence_frequency="daily",
                recurrence_local_time=time(21, 30),
                recurrence_timezone="Asia/Shanghai",
                recurrence_anchor_date=date(2026, 7, 30),
            ),
            admin,
        )

    created = MeetingSeriesScheduler(client.app.state.database).run_once(
        now=datetime(2026, 7, 31, tzinfo=timezone.utc)
    )

    assert len(created) == 1


def test_starting_next_scheduled_occurrence_finishes_the_previous_slot(
    client, project, meeting_users, monkeypatch
):
    admin, member, recorder = meeting_users
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("app.meetings.service.utcnow", lambda: now)
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        series = service.create_series(
            project.id,
            series_payload(
                admin,
                member,
                recorder,
                recurrence_frequency="daily",
                recurrence_local_time=time(21, 30),
                recurrence_timezone="Asia/Shanghai",
                recurrence_anchor_date=date(2026, 7, 30),
            ),
            admin,
        )
        previous, current = service.materialize_due_occurrences(now=now)

        started = service.start(
            current.id,
            LifecycleCommand(expected_version=current.version),
            admin,
        )
        session.refresh(previous)

        assert started.status.value == "in_progress"
        assert previous.status.value == "completed"
        assert [item.status.value for item in previous.agenda_items] == [
            "skipped",
            "skipped",
        ]
        assert previous.current_snapshot is not None
        assert started.series_id == series.id


def test_series_edit_rejects_an_incomplete_recurrence_rule():
    with pytest.raises(ValidationError, match="weekly recurrence requires recurrence_weekday"):
        MeetingSeriesEdit(
            expected_version=1,
            recurrence_frequency="weekly",
            recurrence_interval=1,
            recurrence_local_time=time(9),
            recurrence_timezone="Asia/Shanghai",
            recurrence_anchor_date=date(2026, 7, 30),
        )


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
