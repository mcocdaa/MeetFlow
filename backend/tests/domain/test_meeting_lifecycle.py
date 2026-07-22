import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.agendas.models import AgendaItem
from app.agendas.schemas import AgendaWrite
from app.agendas.service import AgendaService
from app.auth.models import User, UserRole, UserStatus
from app.domain.enums import AgendaStatus, MeetingStatus
from app.errors import AppError
from app.meetings.models import (
    Meeting,
    MeetingAmendment,
    MeetingParticipant,
    MeetingSnapshot,
)
from app.meetings.schemas import (
    AmendmentWrite,
    LifecycleCommand,
    MeetingEdit,
    MeetingWrite,
)
from app.meetings.service import MeetingService
from app.outcomes.models import ActionItem, Decision, DecisionReviewer, OpenQuestion
from app.projects.schemas import ProjectWrite
from app.projects.service import ProjectService

START = datetime(2026, 8, 10, 9, tzinfo=timezone.utc)


@pytest.fixture
def lifecycle_context(client):
    with client.app.state.database.session() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        project = ProjectService(session).create(
            ProjectWrite(
                name="Lifecycle",
                slug="lifecycle",
                status="active",
                lead_user_id=admin.id,
                member_ids=[admin.id],
            ),
            admin,
        )
        meeting = MeetingService(session).create_meeting(
            project.id,
            MeetingWrite(
                title="Trustworthy record",
                purpose_markdown="  # purpose\n",
                summary_markdown="  # summary\n",
                raw_notes_markdown="  raw notes\n",
                scheduled_start=START,
                scheduled_end=START + timedelta(hours=1),
            ),
            admin,
        )
        return admin.id, project.id, meeting.id


def test_finish_rejects_invalid_outcome_source_chain_without_snapshot(
    client, lifecycle_context
):
    admin_id, project_id, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        meeting = session.get(Meeting, meeting_id)
        agenda = AgendaService(session).create(
            meeting_id,
            AgendaWrite(title="Current topic", agenda_type="discussion"),
            actor,
            expected_meeting_version=meeting.version,
        )
        agenda.status = AgendaStatus.completed
        other_project = ProjectService(session).create(
            ProjectWrite(
                name="Other lifecycle",
                slug="other-lifecycle",
                status="active",
                lead_user_id=admin_id,
                member_ids=[admin_id],
            ),
            actor,
        )
        other_meeting = MeetingService(session).create_meeting(
            other_project.id,
            MeetingWrite(
                title="Other meeting",
                scheduled_start=START + timedelta(days=1),
                scheduled_end=START + timedelta(days=1, hours=1),
            ),
            actor,
        )
        other_agenda = AgendaService(session).create(
            other_meeting.id,
            AgendaWrite(title="Other topic", agenda_type="discussion"),
            actor,
            expected_meeting_version=other_meeting.version,
        )
        decision = Decision(
            project_id=other_project.id,
            meeting_id=meeting_id,
            agenda_item_id=agenda.id,
            title="Wrong project",
            decision_markdown="invalid",
            created_by=admin_id,
        )
        action = ActionItem(
            project_id=project_id,
            meeting_id=other_meeting.id,
            agenda_item_id=agenda.id,
            content="Wrong meeting",
            created_by=admin_id,
        )
        question = OpenQuestion(
            project_id=project_id,
            meeting_id=meeting_id,
            agenda_item_id=other_agenda.id,
            question_markdown="Wrong agenda?",
            created_by=admin_id,
        )
        session.add_all([decision, action, question])
        session.commit()
        session.refresh(meeting)
        service = MeetingService(session)
        started = service.start(
            meeting_id, LifecycleCommand(expected_version=meeting.version), actor
        )

        with pytest.raises(AppError) as error:
            service.finish(
                meeting_id, LifecycleCommand(expected_version=started.version), actor
            )

        assert error.value.code == "invalid_outcome_source_chain"
        assert error.value.details == {
            "outcomes": [
                {
                    "outcome_type": "action",
                    "outcome_id": action.id,
                    "project_id": project_id,
                    "meeting_id": other_meeting.id,
                    "agenda_item_id": agenda.id,
                    "violations": ["meeting_id"],
                },
                {
                    "outcome_type": "decision",
                    "outcome_id": decision.id,
                    "project_id": other_project.id,
                    "meeting_id": meeting_id,
                    "agenda_item_id": agenda.id,
                    "violations": ["project_id"],
                },
                {
                    "outcome_type": "open_question",
                    "outcome_id": question.id,
                    "project_id": project_id,
                    "meeting_id": meeting_id,
                    "agenda_item_id": other_agenda.id,
                    "violations": ["agenda_item_id"],
                },
            ]
        }
        assert session.scalar(select(func.count(MeetingSnapshot.id))) == 0
        assert session.get(Meeting, meeting_id).status == MeetingStatus.in_progress


def test_finish_snapshots_full_agenda_chain_and_refinish_is_immutable(
    client, lifecycle_context
):
    admin_id, project_id, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        meeting = session.get(Meeting, meeting_id)
        tied_user = User(
            username="snapshot-tie",
            display_name="Tie",
            password_hash="unused",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add(tied_user)
        session.flush()
        meeting.participants = [
            MeetingParticipant(user_id=tied_user.id, position=0),
            MeetingParticipant(user_id=admin_id, position=0),
        ]
        agenda = AgendaService(session).create(
            meeting_id,
            AgendaWrite(
                title="Architecture", agenda_type="decision", notes_markdown="notes"
            ),
            actor,
            expected_meeting_version=meeting.version,
        )
        agenda.status = AgendaStatus.completed
        session.add_all(
            [
                Decision(
                    project_id=project_id,
                    meeting_id=meeting_id,
                    agenda_item_id=agenda.id,
                    title="Choose SQLite",
                    decision_markdown="**SQLite**",
                    created_by=admin_id,
                    reviewers=[DecisionReviewer(user_id=admin_id)],
                ),
                ActionItem(
                    project_id=project_id,
                    meeting_id=meeting_id,
                    agenda_item_id=agenda.id,
                    content="Ship",
                    owner_user_id=admin_id,
                    created_by=admin_id,
                ),
                OpenQuestion(
                    project_id=project_id,
                    meeting_id=meeting_id,
                    agenda_item_id=agenda.id,
                    question_markdown="What next?",
                    owner_user_id=admin_id,
                    created_by=admin_id,
                ),
                Decision(
                    project_id=project_id,
                    meeting_id=meeting_id,
                    agenda_item_id=None,
                    title="Meeting-level decision",
                    decision_markdown="Direct decision",
                    created_by=admin_id,
                    reviewers=[DecisionReviewer(user_id=admin_id)],
                ),
                ActionItem(
                    project_id=project_id,
                    meeting_id=meeting_id,
                    agenda_item_id=None,
                    content="Meeting-level action",
                    owner_user_id=admin_id,
                    created_by=admin_id,
                ),
                OpenQuestion(
                    project_id=project_id,
                    meeting_id=meeting_id,
                    agenda_item_id=None,
                    question_markdown="Meeting-level question?",
                    owner_user_id=admin_id,
                    created_by=admin_id,
                ),
            ]
        )
        session.commit()
        session.refresh(meeting)
        service = MeetingService(session)
        service.start(
            meeting_id, LifecycleCommand(expected_version=meeting.version), actor
        )
        session.refresh(meeting)
        completed = service.finish(
            meeting_id, LifecycleCommand(expected_version=meeting.version), actor
        )
        first_snapshot_id = completed.current_snapshot_id
        first_json = json.dumps(
            completed.current_snapshot.snapshot_json, sort_keys=True
        )
        document = completed.current_snapshot.snapshot_json
        assert [
            row["user_id"] for row in document["meeting"]["participants"]
        ] == sorted([admin_id, tied_user.id])
        assert document["meeting"]["purpose_markdown"] == "  # purpose\n"
        assert document["agenda_items"][0]["id"] == agenda.id
        assert (
            document["agenda_items"][0]["decisions"][0]["reviewers"][0]["user_id"]
            == admin_id
        )
        assert document["agenda_items"][0]["actions"][0]["content"] == "Ship"
        assert (
            document["agenda_items"][0]["open_questions"][0]["question_markdown"]
            == "What next?"
        )
        assert document["meeting_decisions"][0]["title"] == "Meeting-level decision"
        assert document["meeting_decisions"][0]["reviewers"][0]["user_id"] == admin_id
        assert document["meeting_actions"][0]["content"] == "Meeting-level action"
        assert (
            document["meeting_open_questions"][0]["question_markdown"]
            == "Meeting-level question?"
        )
        assert len(document["agenda_items"][0]["decisions"]) == 1
        json.dumps(document)

        reopened = service.reopen(
            meeting_id, LifecycleCommand(expected_version=completed.version), actor
        )
        assert reopened.current_snapshot_id == first_snapshot_id
        assert reopened.completed_at is None
        refinished = service.finish(
            meeting_id, LifecycleCommand(expected_version=reopened.version), actor
        )
        assert [
            row.completion_number for row in service.list_snapshots(meeting_id)
        ] == [1, 2]
        assert refinished.current_snapshot_id != first_snapshot_id
        assert (
            json.dumps(
                session.get(MeetingSnapshot, first_snapshot_id).snapshot_json,
                sort_keys=True,
            )
            == first_json
        )

        old_version = refinished.version
        amendment = service.add_amendment(
            meeting_id,
            AmendmentWrite(
                reason="Correction",
                content_markdown="  exact fix\n",
                expected_version=old_version,
            ),
            actor,
        )
        assert amendment.content_markdown == "  exact fix\n"
        assert (
            json.dumps(
                session.get(MeetingSnapshot, first_snapshot_id).snapshot_json,
                sort_keys=True,
            )
            == first_json
        )
        with pytest.raises(AppError) as duplicate:
            service.add_amendment(
                meeting_id,
                AmendmentWrite(
                    reason="Correction",
                    content_markdown="duplicate",
                    expected_version=old_version,
                ),
                actor,
            )
        assert duplicate.value.code == "version_conflict"
        assert session.scalar(select(func.count(MeetingAmendment.id))) == 1


def test_simultaneous_finish_creates_one_snapshot(client, lifecycle_context):
    admin_id, _, meeting_id = lifecycle_context
    database = client.app.state.database
    with database.session() as seed:
        service = MeetingService(seed)
        meeting = service.start(
            meeting_id, LifecycleCommand(expected_version=1), seed.get(User, admin_id)
        )
        expected = meeting.version

    with database.session() as stale, database.session() as winner:
        stale_service = MeetingService(stale)
        stale_actor = stale.get(User, admin_id)
        stale_meeting = stale_service.get_meeting(meeting_id)
        winner_service = MeetingService(winner)
        winner_result = winner_service.finish(
            meeting_id,
            LifecycleCommand(expected_version=expected),
            winner.get(User, admin_id),
        )
        assert winner_result.status == MeetingStatus.completed

        with pytest.raises(AppError) as conflict:
            stale_service.finish(
                stale_meeting.id,
                LifecycleCommand(expected_version=expected),
                stale_actor,
            )
        assert conflict.value.code == "version_conflict"
        assert conflict.value.details == {
            "expected_version": expected,
            "actual_version": expected + 1,
        }

    with database.session() as verify:
        assert verify.scalar(select(func.count(MeetingSnapshot.id))) == 1


def test_finish_loses_atomically_to_concurrent_agenda_write(client, lifecycle_context):
    admin_id, _, meeting_id = lifecycle_context
    database = client.app.state.database
    with database.session() as seed:
        meeting = MeetingService(seed).start(
            meeting_id, LifecycleCommand(expected_version=1), seed.get(User, admin_id)
        )
        expected = meeting.version

    with database.session() as stale, database.session() as winner:
        stale_service = MeetingService(stale)
        stale_actor = stale.get(User, admin_id)
        stale_service.get_meeting(meeting_id)
        winner_meeting = winner.get(Meeting, meeting_id)
        AgendaService(winner).create(
            meeting_id,
            AgendaWrite(title="Concurrent topic", agenda_type="discussion"),
            winner.get(User, admin_id),
            expected_meeting_version=winner_meeting.version,
        )

        with pytest.raises(AppError) as conflict:
            stale_service.finish(
                meeting_id, LifecycleCommand(expected_version=expected), stale_actor
            )
        assert conflict.value.code == "version_conflict"

    with database.session() as verify:
        assert verify.scalar(select(func.count(MeetingSnapshot.id))) == 0
        assert verify.get(Meeting, meeting_id).status == MeetingStatus.in_progress
        assert verify.scalar(select(func.count(AgendaItem.id))) == 1


@pytest.mark.parametrize("winner", ["finish", "cancel"])
def test_finish_and_cancel_race_has_one_trustworthy_winner(
    client, lifecycle_context, winner
):
    admin_id, _, meeting_id = lifecycle_context
    database = client.app.state.database
    with database.session() as seed:
        meeting = MeetingService(seed).start(
            meeting_id, LifecycleCommand(expected_version=1), seed.get(User, admin_id)
        )
        expected = meeting.version

    with database.session() as first, database.session() as second:
        first_service = MeetingService(first)
        second_service = MeetingService(second)
        first_actor = first.get(User, admin_id)
        second_actor = second.get(User, admin_id)
        first_service.get_meeting(meeting_id)
        second_service.get_meeting(meeting_id)

        if winner == "finish":
            won = first_service.finish(
                meeting_id, LifecycleCommand(expected_version=expected), first_actor
            )
            assert won.status == MeetingStatus.completed

            def losing_call():
                return second_service.cancel(
                    meeting_id,
                    LifecycleCommand(expected_version=expected),
                    second_actor,
                )

            expected_status = MeetingStatus.completed
            expected_snapshots = 1
        else:
            won = first_service.cancel(
                meeting_id, LifecycleCommand(expected_version=expected), first_actor
            )
            assert won.status == MeetingStatus.canceled

            def losing_call():
                return second_service.finish(
                    meeting_id,
                    LifecycleCommand(expected_version=expected),
                    second_actor,
                )

            expected_status = MeetingStatus.canceled
            expected_snapshots = 0

        with pytest.raises(AppError) as conflict:
            losing_call()
        assert conflict.value.code == "version_conflict"
        assert conflict.value.details == {
            "expected_version": expected,
            "actual_version": expected + 1,
        }
        assert second.scalar(select(Meeting.id).where(Meeting.id == meeting_id))

    with database.session() as verify:
        final = verify.get(Meeting, meeting_id)
        assert final.status == expected_status
        assert (
            verify.scalar(select(func.count(MeetingSnapshot.id))) == expected_snapshots
        )
        assert bool(final.current_snapshot_id) is bool(expected_snapshots)


def test_snapshot_history_pagination_can_reach_beyond_first_two_hundred(
    client, lifecycle_context
):
    admin_id, _, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        session.add_all(
            [
                MeetingSnapshot(
                    meeting_id=meeting_id,
                    completion_number=number,
                    snapshot_json={"number": number},
                    created_by=admin_id,
                )
                for number in range(1, 202)
            ]
        )
        session.commit()
        page = MeetingService(session).list_snapshots(meeting_id, limit=2, offset=199)
        assert [row.completion_number for row in page] == [200, 201]


def test_public_lifecycle_transitions_and_terminal_edit_locks(
    client, lifecycle_context
):
    admin_id, project_id, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        service = MeetingService(session)

        ready = service.mark_ready(
            meeting_id, LifecycleCommand(expected_version=1), actor
        )
        draft = service.mark_draft(
            meeting_id, LifecycleCommand(expected_version=ready.version), actor
        )
        ready_again = service.mark_ready(
            meeting_id, LifecycleCommand(expected_version=draft.version), actor
        )
        started = service.start(
            meeting_id,
            LifecycleCommand(expected_version=ready_again.version),
            actor,
        )
        completed = service.finish(
            meeting_id, LifecycleCommand(expected_version=started.version), actor
        )
        assert completed.status == MeetingStatus.completed

        with pytest.raises(AppError) as completed_edit:
            service.update_meeting(
                meeting_id,
                MeetingEdit(expected_version=completed.version, title="Rewrite"),
                actor,
            )
        assert completed_edit.value.code == "meeting_locked"

        cancel_target = service.create_meeting(
            project_id,
            MeetingWrite(
                title="Canceled meeting",
                scheduled_start=START + timedelta(days=1),
                scheduled_end=START + timedelta(days=1, hours=1),
            ),
            actor,
        )
        canceled = service.cancel(
            cancel_target.id,
            LifecycleCommand(expected_version=cancel_target.version),
            actor,
        )
        assert canceled.status == MeetingStatus.canceled

        with pytest.raises(AppError) as canceled_edit:
            service.update_meeting(
                cancel_target.id,
                MeetingEdit(expected_version=canceled.version, title="Rewrite"),
                actor,
            )
        assert canceled_edit.value.code == "meeting_locked"
