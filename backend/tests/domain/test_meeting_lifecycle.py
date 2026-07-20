import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.agendas.models import AgendaItem
from app.agendas.schemas import AgendaWrite
from app.agendas.service import AgendaService
from app.auth.models import User
from app.domain.enums import AgendaStatus, MeetingStatus, ParticipationRole
from app.errors import AppError
from app.meetings.models import Meeting, MeetingAmendment, MeetingSnapshot
from app.meetings.schemas import (
    AmendmentWrite,
    LifecycleCommand,
    MeetingEdit,
    SnapshotParticipant,
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


def test_lifecycle_schemas_are_strict_and_require_safe_versions():
    assert LifecycleCommand(expected_version=1).expected_version == 1
    with pytest.raises(ValidationError):
        LifecycleCommand(expected_version=0)
    with pytest.raises(ValidationError):
        LifecycleCommand(expected_version=1, unknown=True)
    amendment = AmendmentWrite(
        reason="  typo  ", content_markdown="  exact markdown\n", expected_version=2
    )
    assert amendment.reason == "typo"
    assert amendment.content_markdown == "  exact markdown\n"

    with pytest.raises(ValidationError):
        SnapshotParticipant(
            user_id="user-1",
            participation_role=ParticipationRole.attendee,
            position=0,
            unknown="not part of the signed document",
        )
    with pytest.raises(ValidationError):
        SnapshotParticipant(
            user_id=123,
            participation_role=ParticipationRole.attendee,
            position=0,
        )


def test_transitions_are_versioned_and_invalid_transition_is_explicit(
    client, lifecycle_context
):
    admin_id, _, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        service = MeetingService(session)
        actor = session.get(User, admin_id)
        ready = service.mark_ready(
            meeting_id, LifecycleCommand(expected_version=1), actor
        )
        assert (ready.status, ready.version) == (MeetingStatus.ready, 2)
        started = service.start(meeting_id, LifecycleCommand(expected_version=2), actor)
        assert started.status == MeetingStatus.in_progress
        assert started.started_at is not None

        with pytest.raises(AppError) as error:
            service.mark_ready(meeting_id, LifecycleCommand(expected_version=3), actor)
        assert error.value.code == "invalid_meeting_transition"
        assert error.value.details == {"from": "in_progress", "to": "ready"}

        with pytest.raises(AppError) as stale:
            service.cancel(meeting_id, LifecycleCommand(expected_version=2), actor)
        assert stale.value.code == "version_conflict"
        assert stale.value.details == {"expected_version": 2, "actual_version": 3}
        assert session.scalar(select(Meeting.id).where(Meeting.id == meeting_id))


def test_finish_rejects_unresolved_agenda_in_stable_order(client, lifecycle_context):
    admin_id, _, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        meeting = session.get(Meeting, meeting_id)
        agenda = AgendaService(session)
        first = agenda.create(
            meeting_id,
            AgendaWrite(title="First", agenda_type="discussion"),
            actor,
            expected_meeting_version=meeting.version,
        )
        session.refresh(meeting)
        second = agenda.create(
            meeting_id,
            AgendaWrite(title="Second", agenda_type="decision"),
            actor,
            expected_meeting_version=meeting.version,
        )
        second.status = AgendaStatus.in_progress
        session.commit()
        session.refresh(meeting)
        service = MeetingService(session)
        service.start(
            meeting_id, LifecycleCommand(expected_version=meeting.version), actor
        )
        session.refresh(meeting)

        with pytest.raises(AppError) as error:
            service.finish(
                meeting_id, LifecycleCommand(expected_version=meeting.version), actor
            )
        assert error.value.code == "meeting_has_unresolved_agenda"
        assert error.value.details == {"agenda_ids": [first.id, second.id]}
        assert session.scalar(select(func.count(MeetingSnapshot.id))) == 0


def test_finish_snapshots_full_agenda_chain_and_refinish_is_immutable(
    client, lifecycle_context
):
    admin_id, project_id, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        meeting = session.get(Meeting, meeting_id)
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


def test_completed_and_canceled_meetings_lock_direct_edits(client, lifecycle_context):
    admin_id, _, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        service = MeetingService(session)
        canceled = service.cancel(
            meeting_id, LifecycleCommand(expected_version=1), actor
        )
        assert canceled.status == MeetingStatus.canceled
        assert canceled.completed_at is None
        with pytest.raises(AppError) as error:
            service.update_meeting(
                meeting_id, MeetingEdit(expected_version=2, title="rewrite"), actor
            )
        assert error.value.code == "meeting_locked"


def test_completed_meeting_locks_direct_edit(client, lifecycle_context):
    admin_id, _, meeting_id = lifecycle_context
    with client.app.state.database.session() as session:
        actor = session.get(User, admin_id)
        service = MeetingService(session)
        started = service.start(meeting_id, LifecycleCommand(expected_version=1), actor)
        completed = service.finish(
            meeting_id, LifecycleCommand(expected_version=started.version), actor
        )
        with pytest.raises(AppError) as error:
            service.update_meeting(
                meeting_id,
                MeetingEdit(expected_version=completed.version, title="rewrite"),
                actor,
            )
        assert error.value.code == "meeting_locked"


def test_lifecycle_routes_require_authentication(client, lifecycle_context):
    _, _, meeting_id = lifecycle_context
    assert (
        client.post(
            f"/api/meetings/{meeting_id}/ready", json={"expected_version": 1}
        ).status_code
        == 401
    )
    assert client.get(f"/api/meetings/{meeting_id}/snapshots").status_code == 401
    assert (
        client.post(
            f"/api/meetings/{meeting_id}/reopen", json={"expected_version": 1}
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"/api/meetings/{meeting_id}/cancel", json={"expected_version": 1}
        ).status_code
        == 401
    )


def test_lifecycle_routes_return_records_and_status_codes(client, lifecycle_context):
    _, _, meeting_id = lifecycle_context
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    ready = client.post(
        f"/api/meetings/{meeting_id}/ready", json={"expected_version": 1}
    )
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    started = client.post(
        f"/api/meetings/{meeting_id}/start", json={"expected_version": 2}
    )
    assert started.status_code == 200
    finished = client.post(
        f"/api/meetings/{meeting_id}/finish", json={"expected_version": 3}
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "completed"
    snapshots = client.get(f"/api/meetings/{meeting_id}/snapshots")
    assert snapshots.status_code == 200
    assert [row["completion_number"] for row in snapshots.json()] == [1]
    amended = client.post(
        f"/api/meetings/{meeting_id}/amendments",
        json={
            "reason": "Correction",
            "content_markdown": "fixed",
            "expected_version": 4,
        },
    )
    assert amended.status_code == 201
    reopened = client.post(
        f"/api/meetings/{meeting_id}/reopen", json={"expected_version": 5}
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "in_progress"
    canceled = client.post(
        f"/api/meetings/{meeting_id}/cancel", json={"expected_version": 6}
    )
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    assert canceled.json()["completed_at"] is None


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
        stale_meeting = stale_service._meeting_for_snapshot(meeting_id)
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
        stale_service._meeting_for_snapshot(meeting_id)
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
        first_service._meeting_for_snapshot(meeting_id)
        second_service._meeting_for_snapshot(meeting_id)

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
