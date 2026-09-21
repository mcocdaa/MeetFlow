from datetime import date, datetime, timezone
import pytest
from sqlalchemy import select

from app.agendas.models import AgendaItem
from app.agendas.outcome_tags import format_action_tag, parse_outcome_tags, rewrite_action_in_notes
from app.agendas.schemas import AgendaEdit, AgendaWrite
from app.agendas.service import AgendaService
from app.auth.models import User, UserRole, UserStatus
from app.domain.enums import ActionStatus
from app.meetings.models import Meeting
from app.meetings.schemas import MeetingWrite
from app.meetings.service import MeetingService
from app.outcomes.schemas import ActionEdit
from app.outcomes.service import OutcomeService
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService


@pytest.fixture
def agenda_context(client):
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        member = User(
            username="test-member",
            display_name="Test Member",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add(member)
        session.commit()
        project = ProjectService(session).create(
            ProjectWrite(
                name="Bidirectional Action Project",
                slug="bidirectional-action-project",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id, member.id],
            ),
            admin,
        )
        meeting = MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Bidirectional Meeting",
                scheduled_start=datetime(2026, 9, 20, 10, tzinfo=timezone.utc),
                scheduled_end=datetime(2026, 9, 20, 11, tzinfo=timezone.utc),
            ),
            admin,
        )
        return admin, member, meeting.id


def test_parse_outcome_tags_extended_syntax():
    md = """
# Agenda Notes
@行动:[done][@alice][2026-10-01] 部署生产环境
@行动:[in_progress][@bob] 联调第三方接口
@行动:[todo] 撰写用户手册
@行动: 传统无括号待办
@决策: 采用方案 A
@开放问题: 是否需要备份？
"""
    tags = parse_outcome_tags(md)
    actions = [t for t in tags if t.kind == "action"]
    assert len(actions) == 4

    assert actions[0].status == ActionStatus.done
    assert actions[0].owner_name == "alice"
    assert actions[0].due_date == date(2026, 10, 1)
    assert actions[0].content == "部署生产环境"

    assert actions[1].status == ActionStatus.in_progress
    assert actions[1].owner_name == "bob"
    assert actions[1].content == "联调第三方接口"

    assert actions[2].status == ActionStatus.open
    assert actions[2].owner_name is None
    assert actions[2].content == "撰写用户手册"

    assert actions[3].status == ActionStatus.open
    assert actions[3].owner_name is None
    assert actions[3].content == "传统无括号待办"


def test_rewrite_action_in_notes():
    notes = """# Notes
- List item
@行动: 第一个待办
@决策: 决定采用方案
@行动:[todo][@bob] 第二个待办
"""
    new_tag = format_action_tag(
        content="第一个待办 (已完成)",
        status=ActionStatus.done,
        owner="alice",
        due_date=date(2026, 10, 5),
    )
    rewritten = rewrite_action_in_notes(notes, "action:0", new_tag)
    assert "@行动:[done][@alice][2026-10-05] 第一个待办 (已完成)" in rewritten
    assert "@行动:[todo][@bob] 第二个待办" in rewritten

    # Now rewrite action:1
    new_tag_1 = format_action_tag(
        content="第二个待办 (进行中)",
        status=ActionStatus.in_progress,
        owner="charlie",
    )
    rewritten_2 = rewrite_action_in_notes(rewritten, "action:1", new_tag_1)
    assert "@行动:[in_progress][@charlie] 第二个待办 (进行中)" in rewritten_2


def test_bidirectional_action_sync_end_to_end(client, agenda_context):
    admin, member, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        agenda_service = AgendaService(session)
        outcome_service = OutcomeService(session)
        meeting = session.get(Meeting, meeting_id)

        agenda = agenda_service.create(
            meeting.id,
            AgendaWrite(title="Architecture Review", agenda_type="discussion"),
            admin,
            expected_meeting_version=meeting.version,
        )

        # 1. Edit notes markdown with extended action syntax
        notes_input = f"""
## 会议研讨记录
@行动:[todo][@{admin.username}][2026-10-15] 实施双向状态机
@行动:[in_progress] 优化SQLite WAL参数
"""
        saved_agenda = agenda_service.update(
            agenda.id,
            AgendaEdit(expected_version=agenda.version, notes_markdown=notes_input),
            admin,
        )

        actions = outcome_service.list_actions(meeting.project_id)
        derived_actions = [a for a in actions if a.agenda_item_id == saved_agenda.id]
        assert len(derived_actions) == 2

        action_0 = next(a for a in derived_actions if a.source_tag_key == "action:0")
        assert action_0.content == "实施双向状态机"
        assert action_0.status == ActionStatus.open
        assert action_0.owner_user_id == admin.id
        assert action_0.due_date == date(2026, 10, 15)

        action_1 = next(a for a in derived_actions if a.source_tag_key == "action:1")
        assert action_1.content == "优化SQLite WAL参数"
        assert action_1.status == ActionStatus.in_progress

        # 2. Update action_0 via OutcomeService (simulating one-click toggle in outcome list)
        updated_action_0 = outcome_service.update_action(
            action_0.id,
            ActionEdit(
                expected_version=action_0.version,
                status=ActionStatus.done,
            ),
            admin,
        )
        assert updated_action_0.status == ActionStatus.done
        assert updated_action_0.completed_at is not None

        # 3. Verify that the agenda item notes_markdown AST has been rewritten!
        refreshed_agenda = session.get(AgendaItem, saved_agenda.id)
        assert f"@行动:[done][@{admin.username}][2026-10-15] 实施双向状态机" in refreshed_agenda.notes_markdown
