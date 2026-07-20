from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select

from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.meetings.models import (
    ActionItem,
    Attachment,
    Meeting,
    MeetingSeries,
    MeetingUpdate,
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
            ),
            admin,
        )
        session.refresh(occurrence)

        assert occurrence.purpose_markdown == "  # Keep exact markdown  \n"
        assert occurrence.host_user_id == admin.id
        assert [row.user_id for row in occurrence.participants] == [member.id, admin.id]


def test_standing_items_are_ordered_and_serialized_but_not_copied_yet(
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
                title="No agenda copy yet",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=45),
            ),
            admin,
        )
        assert not hasattr(occurrence, "agenda_items")


def test_standalone_meeting_has_no_series(client, project, meeting_users):
    admin, member, _ = meeting_users
    with client.app.state.database.session() as session:
        meeting = MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Ad hoc incident review",
                purpose_markdown="Incident notes",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=30),
                participants=[{"user_id": member.id, "participation_role": "attendee"}],
            ),
            admin,
        )
        assert meeting.series_id is None
        assert meeting.project_id == project.id


def test_referenced_projects_and_users_are_validated(client, project, meeting_users):
    admin, member, recorder = meeting_users
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        with pytest.raises(AppError) as error:
            service.create_series(
                "missing", series_payload(admin, member, recorder), admin
            )
        assert error.value.code == "project_not_found"

        with pytest.raises(AppError) as error:
            service.create_series(
                project.id,
                series_payload(
                    admin,
                    member,
                    recorder,
                    default_host_user_id="missing-user",
                ),
                admin,
            )
        assert error.value.code == "user_not_found"
        assert error.value.details == {"user_ids": ["missing-user"]}


def test_schemas_trim_ordinary_text_preserve_markdown_and_validate_time():
    payload = MeetingWrite(
        title="  Review  ",
        purpose_markdown="  markdown stays  \n",
        scheduled_start=START,
        scheduled_end=START + timedelta(minutes=30),
    )
    assert payload.title == "Review"
    assert payload.purpose_markdown == "  markdown stays  \n"

    with pytest.raises(ValidationError):
        MeetingWrite(
            title="Bad time",
            scheduled_start=START,
            scheduled_end=START,
        )


def test_meeting_inputs_require_timezone_and_lifecycle_status_is_command_only():
    with pytest.raises(ValidationError):
        MeetingWrite(
            title="Naive start",
            scheduled_start=START.replace(tzinfo=None),
            scheduled_end=START + timedelta(minutes=30),
        )
    with pytest.raises(ValidationError):
        MeetingWrite(
            title="Lifecycle bypass",
            scheduled_start=START,
            scheduled_end=START + timedelta(minutes=30),
            status="completed",
        )
    with pytest.raises(ValidationError):
        MeetingEdit(expected_version=1, status="completed")

    offset_payload = MeetingWrite(
        title="UTC normalization",
        scheduled_start=datetime(2026, 7, 21, 9, tzinfo=timezone(timedelta(hours=8))),
        scheduled_end=datetime(2026, 7, 21, 10, tzinfo=timezone(timedelta(hours=8))),
    )
    assert offset_payload.scheduled_start == datetime(
        2026, 7, 21, 1, tzinfo=timezone.utc
    )


def test_one_sided_time_edit_handles_sqlite_naive_values(
    client, project, meeting_users
):
    admin, _, _ = meeting_users
    database = client.app.state.database
    with database.session() as session:
        meeting = MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Timezone edit",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=30),
            ),
            admin,
        )
        meeting_id = meeting.id

    with database.session() as session:
        loaded = session.get(Meeting, meeting_id)
        assert loaded.scheduled_start.tzinfo is None  # SQLite storage behavior.
        edited = MeetingService(session).update_meeting(
            meeting_id,
            MeetingEdit(
                expected_version=1,
                scheduled_end=START + timedelta(minutes=45),
            ),
            admin,
        )
        assert edited.version == 2


def test_new_meeting_is_always_draft(client, project, meeting_users):
    admin, _, _ = meeting_users
    with client.app.state.database.session() as session:
        meeting = MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Draft only",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=30),
            ),
            admin,
        )
        assert meeting.status.value == "draft"


def test_upload_works_for_new_meeting_and_package_contains_attachment(
    authenticated_client, project, meeting_users
):
    admin, _, _ = meeting_users
    with authenticated_client.app.state.database.session() as session:
        meeting = MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Attachment integration",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=30),
            ),
            admin,
        )
        meeting_id = meeting.id

    uploaded = authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={"file": ("board.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["created_by"]["id"] == admin.id

    with authenticated_client.app.state.database.session() as session:
        package = MeetingService(session).package(meeting_id)
        assert [item["id"] for item in package["attachments"]] == [
            uploaded.json()["id"]
        ]


def test_package_and_plugin_context_include_transitional_rows(
    client, project, meeting_users
):
    admin, _, _ = meeting_users
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        meeting = service.create_meeting(
            project.id,
            MeetingWrite(
                title="Plugin context",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=30),
            ),
            admin,
        )
        session.add_all(
            [
                ActionItem(
                    meeting_id=meeting.id,
                    content="Follow up",
                    created_by=admin.id,
                ),
                MeetingUpdate(
                    meeting_id=meeting.id,
                    content_markdown="Update",
                    created_by=admin.id,
                ),
                Attachment(
                    meeting_id=meeting.id,
                    original_name="notes.txt",
                    stored_name="stored-notes.txt",
                    mime_type="application/octet-stream",
                    size=5,
                    attachment_type="file",
                    created_by=admin.id,
                ),
            ]
        )
        session.commit()

        package = service.package(meeting.id)
        context = service.plugin_context(meeting.id, admin)

        assert package["actions"][0]["content"] == "Follow up"
        assert package["updates"][0]["content_markdown"] == "Update"
        assert package["attachments"][0]["original_name"] == "notes.txt"
        assert context["attachments"] == package["attachments"]
        assert context["project"] == project.name


def test_detail_serialization_has_bounded_relationship_queries(
    client, project, meeting_users
):
    admin, member, recorder = meeting_users
    database = client.app.state.database
    with database.session() as seed:
        service = MeetingService(seed)
        series = service.create_series(
            project.id, series_payload(admin, member, recorder), admin
        )
        meeting = service.create_occurrence(
            series.id,
            OccurrenceWrite(
                title="Bounded detail",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=45),
            ),
            admin,
        )
        series_id, meeting_id = series.id, meeting.id

    with database.session() as session:
        statements = []

        def count_query(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        event.listen(database.engine, "before_cursor_execute", count_query)
        try:
            series_body = MeetingService(session).series_detail(series_id)
            series_queries = len(statements)
            statements.clear()
            meeting_body = MeetingService(session).meeting_detail(meeting_id)
            meeting_queries = len(statements)
        finally:
            event.remove(database.engine, "before_cursor_execute", count_query)

        assert len(series_body["participants"]) == 2
        assert len(series_body["standing_items"]) == 2
        assert len(meeting_body["participants"]) == 2
        assert series_queries <= 3
        assert meeting_queries <= 2


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


def test_missing_series_and_meeting_return_domain_errors(client, meeting_users):
    admin, _, _ = meeting_users
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        with pytest.raises(AppError) as error:
            service.get_series("missing")
        assert error.value.code == "meeting_series_not_found"
        with pytest.raises(AppError) as error:
            service.get_meeting("missing")
        assert error.value.code == "meeting_not_found"


def test_meeting_domain_routes_require_authentication(client):
    assert client.get("/api/projects/missing/meeting-series").status_code == 401
    assert client.get("/api/projects/missing/meetings").status_code == 401
    assert client.get("/api/meeting-series/missing").status_code == 401
    assert client.get("/api/meetings/missing").status_code == 401


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


def test_project_delete_guard_uses_project_foreign_key(client, project, meeting_users):
    admin, _, _ = meeting_users
    with client.app.state.database.session() as session:
        MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Blocks deletion",
                scheduled_start=START,
                scheduled_end=START + timedelta(minutes=30),
            ),
            admin,
        )
        with pytest.raises(AppError) as error:
            ProjectService(session).delete(project.id, admin)
        assert error.value.code == "project_not_empty"
