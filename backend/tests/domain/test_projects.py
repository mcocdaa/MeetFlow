from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.meetings.models import Meeting
from app.projects.models import Project
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


def test_concurrent_project_update_is_atomic(client, users):
    admin, _, _ = users
    database = client.app.state.database
    with database.session() as seed_session:
        project = ProjectService(seed_session).create(project_payload(admin), admin)
        project_id = project.id

    with database.session() as first_session, database.session() as second_session:
        first = first_session.get(Project, project_id)
        second = second_session.get(Project, project_id)
        assert first.version == second.version == 1

        ProjectService(first_session).update(
            project_id,
            ProjectEdit(expected_version=1, name="First writer"),
            admin,
        )
        with pytest.raises(AppError) as error:
            ProjectService(second_session).update(
                project_id,
                ProjectEdit(expected_version=1, name="Second writer"),
                admin,
            )

        assert error.value.code == "version_conflict"
        assert error.value.details == {
            "expected_version": 1,
            "actual_version": 2,
        }
        assert second_session.get(Project, project_id).name == "First writer"
        assert second_session.scalar(select(func.count(Project.id))) == 1


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
            project_id=project.id,
            scheduled_start=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 7, 20, 11, tzinfo=timezone.utc),
            created_by=admin.id,
            updated_by=admin.id,
        )
        session.add(meeting)
        session.commit()
        with pytest.raises(AppError) as error:
            service.delete(project.id, admin)
        assert error.value.code == "project_not_empty"
