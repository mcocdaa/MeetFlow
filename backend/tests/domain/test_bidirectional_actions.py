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


def test_parse_outcome_tags_chinese_status_tokens():
    md = """
@行动:[待办][@林宇][2026-10-01] 整理压测报告
@行动:[待开始][@乔安] 准备回滚预案
@行动:[进行中][@林宇] 推进网关限流改造
@行动:[已完成][@乔安][2026-09-30] 完成发布清单核验
@行动:[已取消] 旧版接口迁移计划
"""
    tags = parse_outcome_tags(md)
    assert len(tags) == 5

    assert tags[0].status == ActionStatus.open
    assert tags[0].owner_name == "林宇"
    assert tags[0].due_date == date(2026, 10, 1)
    assert tags[0].content == "整理压测报告"

    assert tags[1].status == ActionStatus.open
    assert tags[1].owner_name == "乔安"
    assert tags[1].content == "准备回滚预案"

    assert tags[2].status == ActionStatus.in_progress
    assert tags[2].owner_name == "林宇"
    assert tags[2].content == "推进网关限流改造"

    assert tags[3].status == ActionStatus.done
    assert tags[3].owner_name == "乔安"
    assert tags[3].due_date == date(2026, 9, 30)
    assert tags[3].content == "完成发布清单核验"

    assert tags[4].status == ActionStatus.canceled
    assert tags[4].owner_name is None
    assert tags[4].content == "旧版接口迁移计划"


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


def test_parse_outcome_tags_fenced_code_blocks_brackets_and_question_aliases():
    md = """
# 议题记录
```markdown
@决策: 代码块内的示例决策不应提取
@行动:[done] 代码块内的示例行动不应提取
@问题: 代码块内的示例问题不应提取
```
~~~
@开放问题: 波浪号代码块内也不应提取
~~~
@行动:[todo][@alice][P0] 修复核心缺陷
@问题: 简写问题标签是否生效？
@开放问题: 完整开放问题标签是否生效？
"""
    tags = parse_outcome_tags(md)
    assert len(tags) == 3
    assert tags[0].kind == "action"
    assert tags[0].owner_name == "alice"
    assert tags[0].content == "[P0] 修复核心缺陷"
    assert tags[1].kind == "question"
    assert tags[1].content == "简写问题标签是否生效？"
    assert tags[2].kind == "question"
    assert tags[2].content == "完整开放问题标签是否生效？"

    # Verify rewrite_action_in_notes also skips fenced code blocks
    rewritten = rewrite_action_in_notes(
        md,
        "action:0",
        format_action_tag(content="[P0] 修复核心缺陷", status=ActionStatus.done, owner="alice"),
    )
    assert "@行动:[done] 代码块内的示例行动不应提取" in rewritten
    assert "@行动:[done][@alice] [P0] 修复核心缺陷" in rewritten


def test_reconcile_outcomes_preserves_final_decision_clears_metadata_and_handles_duplicate_names(
    client, agenda_context
):
    _, _, meeting_id = agenda_context
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        member = session.scalar(select(User).where(User.username == "test-member"))
        member_id = member.id
        # Add another active user with duplicate display_name and an inactive user
        dup_member = User(
            username="dup-member",
            display_name="Test Member",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        inactive_user = User(
            username="inactive-owner",
            display_name="Inactive Owner",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.DISABLED,
        )
        session.add_all([dup_member, inactive_user])
        session.commit()
        dup_member_id = dup_member.id
        admin = session.scalar(select(User).where(User.username == "admin"))

        agenda_service = AgendaService(session)
        outcome_service = OutcomeService(session)
        meeting = session.get(Meeting, meeting_id)

        agenda = agenda_service.create(
            meeting.id,
            AgendaWrite(title="Reconciliation Edge Cases", agenda_type="decision"),
            admin,
            expected_meeting_version=meeting.version,
        )

        # 1. Create initial decision and action with owner + due_date
        agenda = agenda_service.update(
            agenda.id,
            AgendaEdit(
                expected_version=agenda.version,
                notes_markdown=(
                    "@决策: 核心架构定稿\n"
                    "@行动:[todo][@Test Member][2026-10-20] 编写接口文档\n"
                    "@行动:[todo][@inactive-owner] 已禁用用户任务\n"
                ),
            ),
            admin,
        )

        from app.outcomes.models import Decision
        from app.outcomes.schemas import DecisionFinalizeWrite

        decisions = [
            d
            for d in outcome_service.list_decisions(meeting.project_id)
            if d.agenda_item_id == agenda.id
        ]
        assert len(decisions) == 1
        final_dec = outcome_service.finalize_decision(
            decisions[0].id,
            DecisionFinalizeWrite(expected_version=decisions[0].version),
            admin,
        )
        assert final_dec.status.value == "final"

        actions = [
            a
            for a in outcome_service.list_actions(meeting.project_id)
            if a.agenda_item_id == agenda.id
        ]
        doc_action = next(a for a in actions if a.content == "编写接口文档")
        assert doc_action.owner_user_id in {member_id, dup_member_id}
        assert doc_action.due_date == date(2026, 10, 20)

        inactive_action = next(a for a in actions if a.content == "已禁用用户任务")
        assert inactive_action.owner_user_id is None

        # 2. Insert a new decision BEFORE the finalized decision and remove owner/due_date from action
        agenda = session.get(AgendaItem, agenda.id)
        agenda = agenda_service.update(
            agenda.id,
            AgendaEdit(
                expected_version=agenda.version,
                notes_markdown=(
                    "@决策: 前置新增决议\n"
                    "@决策: 核心架构定稿\n"
                    "@行动:[in_progress] 编写接口文档\n"
                ),
            ),
            admin,
        )

        session.refresh(final_dec)
        assert final_dec.status.value == "final"
        assert final_dec.title == "核心架构定稿"
        assert final_dec.source_tag_key == "decision:1"

        session.refresh(doc_action)
        assert doc_action.status == ActionStatus.in_progress
        assert doc_action.owner_user_id is None
        assert doc_action.due_date is None

        # 3. Even if all @决策 tags are removed from notes, finalized decision must not be deleted
        agenda = agenda_service.update(
            agenda.id,
            AgendaEdit(
                expected_version=agenda.version,
                notes_markdown="@行动:[done] 编写接口文档\n",
            ),
            admin,
        )
        assert session.get(Decision, final_dec.id) is not None
        assert session.get(Decision, final_dec.id).status.value == "final"


def test_parse_and_rewrite_english_outcome_tags():
    md = """# Meeting Notes
@Decision: Adopt canonical REST API contract
@Action:[todo][@alice][2026-10-18] Ship bilingual UI toggle
@Question: Should we preserve legacy webhook aliases?
"""
    tags = parse_outcome_tags(md)
    assert len(tags) == 3
    assert tags[0].kind == "decision"
    assert tags[0].source_tag_key == "decision:0"
    assert tags[0].content == "Adopt canonical REST API contract"

    assert tags[1].kind == "action"
    assert tags[1].source_tag_key == "action:0"
    assert tags[1].status == ActionStatus.open
    assert tags[1].owner_name == "alice"
    assert tags[1].due_date == date(2026, 10, 18)
    assert tags[1].content == "Ship bilingual UI toggle"

    assert tags[2].kind == "question"
    assert tags[2].source_tag_key == "question:0"
    assert tags[2].content == "Should we preserve legacy webhook aliases?"

    # Rewriting an English @Action: tag preserves the @Action: prefix
    new_tag = format_action_tag(
        content="Ship bilingual UI toggle",
        status=ActionStatus.done,
        owner="alice",
        due_date=date(2026, 10, 18),
    )
    rewritten = rewrite_action_in_notes(md, "action:0", new_tag)
    assert "@Action:[done][@alice][2026-10-18] Ship bilingual UI toggle" in rewritten

