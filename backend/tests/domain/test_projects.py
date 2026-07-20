from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.meetings.models import Meeting
from app.projects.models import Project, ProjectMember, ProjectUpdate
from app.projects.schemas import ProjectEdit, ProjectUpdateWrite, ProjectWrite
from app.projects.service import ProjectService


@pytest.fixture
def users(client):
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        member = User(
            username="member",
            display_name="Member",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        outsider = User(
            username="outsider",
            display_name="Outsider",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add_all([member, outsider])
        session.commit()
        for user in (admin, member, outsider):
            session.refresh(user)
        yield admin, member, outsider


def project_payload(admin, member=None, **overrides):
    values = {
        "name": "MeetFlow",
        "slug": "meetflow",
        "summary": "Project workspace",
        "description_markdown": "  # Keep markdown  \n",
        "status": "active",
        "health": "on_track",
        "lead_user_id": admin.id,
        "target_date": date(2026, 12, 31),
        "member_ids": [admin.id] + ([member.id] if member else []),
    }
    values.update(overrides)
    return ProjectWrite(**values)


def test_project_write_trims_ordinary_strings_before_validation():
    payload = ProjectWrite(
        name="  MeetFlow  ",
        slug="  meetflow  ",
        summary="  Project workspace  ",
        description_markdown="  # Keep markdown  \n",
        status=" active ",
        health=" on_track ",
        lead_user_id="  user-1  ",
        member_ids=["  user-1  ", " user-2 "],
    )

    assert payload.name == "MeetFlow"
    assert payload.slug == "meetflow"
    assert payload.summary == "Project workspace"
    assert payload.description_markdown == "  # Keep markdown  \n"
    assert payload.status.value == "active"
    assert payload.health.value == "on_track"
    assert payload.lead_user_id == "user-1"
    assert payload.member_ids == ["user-1", "user-2"]


def test_project_edit_trims_lead_before_lookup_and_persistence(client, users):
    admin, member, _ = users
    with client.app.state.database.session() as session:
        service = ProjectService(session)
        project = service.create(project_payload(admin), admin)
        edited = service.update(
            project.id,
            ProjectEdit(
                expected_version=1,
                lead_user_id=f"  {member.id}  ",
                description_markdown="  preserved edit markdown  \n",
            ),
            admin,
        )

        assert edited.lead_user_id == member.id
        assert edited.description_markdown == "  preserved edit markdown  \n"


def test_project_edit_rejects_whitespace_only_lead_id():
    with pytest.raises(ValueError):
        ProjectEdit(expected_version=1, lead_user_id="   ")

    assert ProjectEdit(expected_version=1, lead_user_id=None).lead_user_id is None


def test_project_has_members_health_and_version(client, users):
    admin, member, _ = users
    with client.app.state.database.session() as session:
        project = ProjectService(session).create(
            project_payload(admin, member), actor=admin
        )
        assert project.version == 1
        assert project.health.value == "on_track"
        assert project.description_markdown == "  # Keep markdown  \n"
        assert {row.user_id for row in project.memberships} == {
            admin.id,
            member.id,
        }


def test_stale_project_update_is_rejected(client, users):
    admin, _, _ = users
    with client.app.state.database.session() as session:
        project = ProjectService(session).create(project_payload(admin), admin)
        with pytest.raises(AppError) as error:
            ProjectService(session).update(
                project.id,
                ProjectEdit(expected_version=0, name="Changed"),
                admin,
            )
        assert error.value.code == "version_conflict"
        assert error.value.details == {
            "expected_version": 0,
            "actual_version": 1,
        }


def test_project_update_keeps_human_or_applied_ai_source(client, users):
    admin, _, _ = users
    with client.app.state.database.session() as session:
        project = ProjectService(session).create(project_payload(admin), admin)
        human = ProjectService(session).create_update(
            project.id,
            ProjectUpdateWrite(
                health="on_track",
                content_markdown="  Human markdown  \n",
                source="human",
            ),
            admin,
        )
        ai = ProjectService(session).create_update(
            project.id,
            ProjectUpdateWrite(
                health="at_risk",
                content_markdown="AI draft accepted",
                source="ai_draft_applied",
            ),
            admin,
        )
        assert human.source.value == "human"
        assert human.content_markdown == "  Human markdown  \n"
        assert ai.source.value == "ai_draft_applied"


def test_http_conflict_includes_version_details(authenticated_client, users):
    admin, _, _ = users
    created = authenticated_client.post(
        "/api/projects", json=project_payload(admin).model_dump(mode="json")
    )
    assert created.status_code == 201
    response = authenticated_client.put(
        f"/api/projects/{created.json()['id']}",
        json={"expected_version": 0, "name": "Changed"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {
        "expected_version": 0,
        "actual_version": 1,
    }


def test_missing_member_is_rejected_and_duplicate_members_are_deduplicated(
    client, users
):
    admin, member, _ = users
    with client.app.state.database.session() as session:
        with pytest.raises(AppError) as error:
            ProjectService(session).create(
                project_payload(admin, member_ids=["missing"]), admin
            )
        assert error.value.code == "user_not_found"

        project = ProjectService(session).create(
            project_payload(
                admin,
                member_ids=[member.id, admin.id, member.id, admin.id],
            ),
            admin,
        )
        assert [row.user_id for row in project.memberships] == [
            member.id,
            admin.id,
        ]


def test_duplicate_slug_leaves_session_reusable(client, users):
    admin, _, _ = users
    with client.app.state.database.session() as session:
        service = ProjectService(session)
        service.create(project_payload(admin), admin)
        with pytest.raises(AppError) as error:
            service.create(project_payload(admin, name="Duplicate"), admin)
        assert error.value.code == "project_slug_conflict"
        assert session.scalar(select(func.count(Project.id))) == 1


def test_membership_replacement_increments_version_once(client, users):
    admin, member, outsider = users
    with client.app.state.database.session() as session:
        service = ProjectService(session)
        project = service.create(project_payload(admin, member), admin)
        updated = service.update(
            project.id,
            ProjectEdit(
                expected_version=1,
                summary="  Revised summary  ",
                member_ids=[outsider.id, outsider.id],
            ),
            member,
        )
        assert updated.version == 2
        assert updated.summary == "Revised summary"
        assert [row.user_id for row in updated.memberships] == [outsider.id]


def test_progress_update_requires_membership_but_admin_is_always_allowed(
    client, users
):
    admin, member, outsider = users
    with client.app.state.database.session() as session:
        service = ProjectService(session)
        project = service.create(project_payload(admin, member), admin)
        with pytest.raises(AppError) as error:
            service.create_update(
                project.id,
                ProjectUpdateWrite(content_markdown="No access"),
                outsider,
            )
        assert error.value.code == "project_membership_required"
        assert service.create_update(
            project.id,
            ProjectUpdateWrite(content_markdown="Admin update"),
            admin,
        )


def test_only_update_author_or_admin_can_edit(client, users):
    admin, member, outsider = users
    with client.app.state.database.session() as session:
        service = ProjectService(session)
        project = service.create(
            project_payload(admin, member_ids=[member.id, outsider.id]), admin
        )
        update = service.create_update(
            project.id,
            ProjectUpdateWrite(content_markdown="Original"),
            member,
        )
        with pytest.raises(AppError) as error:
            service.edit_update(
                update.id,
                ProjectUpdateWrite(content_markdown="Hijacked"),
                outsider,
            )
        assert error.value.code == "project_update_forbidden"
        edited = service.edit_update(
            update.id,
            ProjectUpdateWrite(content_markdown="Admin correction"),
            admin,
        )
        assert edited.content_markdown == "Admin correction"


def test_delete_requires_admin_or_lead_and_rejects_nonempty_project(client, users):
    admin, member, outsider = users
    with client.app.state.database.session() as session:
        service = ProjectService(session)
        project = service.create(project_payload(admin, member), admin)
        with pytest.raises(AppError) as error:
            service.delete(project.id, outsider)
        assert error.value.code == "project_delete_forbidden"

        meeting = Meeting(
            title="Existing meeting",
            project=project.name,
            meeting_type="technical",
            meeting_date=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
            participants=[],
            raw_notes_markdown="",
            conclusions_markdown="",
            created_by=admin.id,
            updated_by=admin.id,
        )
        session.add(meeting)
        session.commit()
        with pytest.raises(AppError) as error:
            service.delete(project.id, admin)
        assert error.value.code == "project_not_empty"


def test_project_routes_require_authentication(client):
    assert client.get("/api/projects").status_code == 401
    assert client.put(
        "/api/project-updates/missing",
        json={"content_markdown": "No auth"},
    ).status_code == 401


def test_project_api_serializes_members_and_updates(authenticated_client, users):
    admin, member, _ = users
    created = authenticated_client.post(
        "/api/projects",
        json=project_payload(admin, member).model_dump(mode="json"),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["lead"]["id"] == admin.id
    assert [item["user"]["id"] for item in body["memberships"]] == [
        admin.id,
        member.id,
    ]

    update = authenticated_client.post(
        f"/api/projects/{body['id']}/updates",
        json={"content_markdown": "Progress", "health": "on_track"},
    )
    assert update.status_code == 201
    detail = authenticated_client.get(f"/api/projects/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["updates"][0]["content_markdown"] == "Progress"
