from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.auth.models import User, UserRole, UserStatus
from app.domain.enums import ParticipationRole, ProjectMemberRole
from app.meetings.models import Meeting, MeetingParticipant
from app.projects.models import ProjectMember
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService


@dataclass
class AccessRows:
    admin: User
    lead: User
    member: User
    stakeholder: User
    outsider: User
    invited: User
    project_id: str
    meeting_id: str


def _active_user(username: str) -> User:
    return User(
        username=username,
        display_name=username.title(),
        password_hash="unused",
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
    )


def test_workspace_access_distinguishes_roles(client):
    from app.projects.access import WorkspaceAccess

    database = client.app.state.database
    with database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        lead, member, stakeholder, outsider, invited = (
            _active_user("access-lead"),
            _active_user("access-member"),
            _active_user("access-stakeholder"),
            _active_user("access-outsider"),
            _active_user("access-invited"),
        )
        session.add_all([lead, member, stakeholder, outsider, invited])
        session.commit()

        project = ProjectService(session).create(
            ProjectWrite(
                name="Access project",
                slug="access-project",
                lead_user_id=lead.id,
                member_ids=[lead.id, member.id, stakeholder.id],
            ),
            admin,
        )
        session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == stakeholder.id,
            )
        ).role = ProjectMemberRole.stakeholder
        meeting = Meeting(
            project_id=project.id,
            title="Access meeting",
            scheduled_start=datetime(2026, 8, 1, 9, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
            created_by=lead.id,
            updated_by=lead.id,
            participants=[
                MeetingParticipant(
                    user_id=invited.id,
                    participation_role=ParticipationRole.attendee,
                    position=0,
                )
            ],
        )
        session.add(meeting)
        session.commit()

        rows = AccessRows(
            admin=admin,
            lead=lead,
            member=member,
            stakeholder=stakeholder,
            outsider=outsider,
            invited=invited,
            project_id=project.id,
            meeting_id=meeting.id,
        )
        access = WorkspaceAccess(session)
        loaded_project = access.require_project_view(rows.project_id, rows.lead)
        loaded_meeting = access.require_meeting_view(rows.meeting_id, rows.invited)

        assert access.project_capabilities(loaded_project, rows.admin).can_manage
        assert access.project_capabilities(loaded_project, rows.lead).can_manage
        assert access.project_capabilities(loaded_project, rows.member).can_contribute
        assert not access.project_capabilities(loaded_project, rows.member).can_manage
        assert access.project_capabilities(loaded_project, rows.stakeholder).can_view
        assert not access.project_capabilities(
            loaded_project, rows.stakeholder
        ).can_contribute
        assert not access.project_capabilities(loaded_project, rows.outsider).can_view
        assert access.meeting_capabilities(loaded_meeting, rows.invited).can_view
        assert access.meeting_capabilities(loaded_meeting, rows.invited).can_comment
        assert not access.meeting_capabilities(
            loaded_meeting, rows.invited
        ).can_contribute
