from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from sqlalchemy import event, select

from app.auth.models import User, UserRole, UserStatus
from app.meetings.models import Meeting
from app.outcomes.models import (
    ActionItem,
    Decision,
    DecisionReviewer,
    OpenQuestion,
)

START = datetime(2026, 7, 22, 9, tzinfo=timezone.utc)
_unique = count()


@pytest.fixture
def project(authenticated_client):
    admin = authenticated_client.get("/api/auth/me").json()
    response = authenticated_client.post(
        "/api/projects",
        json={
            "name": "Mutation query project",
            "slug": f"mutation-query-{next(_unique)}",
            "lead_user_id": admin["id"],
            "member_ids": [admin["id"]],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_users(client, amount: int, label: str) -> list[str]:
    with client.app.state.database.session() as session:
        users = [
            User(
                username=f"query-{label}-{next(_unique)}",
                display_name=f"Query user {index}",
                password_hash="unused",
                role=UserRole.MEMBER,
                status=UserStatus.ACTIVE,
            )
            for index in range(amount)
        ]
        session.add_all(users)
        session.commit()
        return [user.id for user in users]


def _select_count(engine, request, expected_status: int = 200):
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = request()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == expected_status, response.text
    return len(statements), response.json()


def _series_payload(user_ids: list[str], title: str) -> dict:
    return {
        "title": title,
        "default_host_user_id": user_ids[0],
        "default_recorder_user_id": user_ids[-1],
        "participants": [
            {"user_id": user_id, "participation_role": "attendee"}
            for user_id in user_ids
        ],
        "standing_items": [
            {
                "title": f"Agenda {index}",
                "agenda_type": "discussion",
                "default_owner_user_id": user_id,
            }
            for index, user_id in enumerate(user_ids)
        ],
    }


def _meeting_payload(user_ids: list[str], title: str) -> dict:
    return {
        "title": title,
        "scheduled_start": START.isoformat(),
        "scheduled_end": (START + timedelta(hours=1)).isoformat(),
        "host_user_id": user_ids[0],
        "recorder_user_id": user_ids[-1],
        "participants": [
            {"user_id": user_id, "participation_role": "attendee"}
            for user_id in user_ids
        ],
    }


def test_series_mutation_responses_have_size_independent_select_counts(
    authenticated_client, project
):
    engine = authenticated_client.app.state.database.engine
    small_users = _create_users(authenticated_client, 1, "series-small")
    large_users = _create_users(authenticated_client, 16, "series-large")

    create_counts = []
    created = []
    for label, user_ids in (("small", small_users), ("large", large_users)):
        query_count, body = _select_count(
            engine,
            lambda label=label, user_ids=user_ids: authenticated_client.post(
                f"/api/projects/{project['id']}/meeting-series",
                json=_series_payload(user_ids, f"Series {label}"),
            ),
            expected_status=201,
        )
        assert len(body["participants"]) == len(user_ids)
        assert len(body["standing_items"]) == len(user_ids)
        create_counts.append(query_count)
        created.append(body)

    update_counts = []
    for label, body in zip(("small", "large"), created, strict=True):
        query_count, updated = _select_count(
            engine,
            lambda label=label, body=body: authenticated_client.put(
                f"/api/meeting-series/{body['id']}",
                json={"expected_version": body["version"], "title": f"Updated {label}"},
            ),
        )
        assert updated["title"] == f"Updated {label}"
        update_counts.append(query_count)

    assert max(create_counts) <= 8
    assert max(create_counts) - min(create_counts) <= 1
    assert max(update_counts) <= 10
    assert max(update_counts) - min(update_counts) <= 1


def test_meeting_creation_responses_have_size_independent_select_counts(
    authenticated_client, project
):
    engine = authenticated_client.app.state.database.engine
    small_users = _create_users(authenticated_client, 1, "meeting-small")
    large_users = _create_users(authenticated_client, 16, "meeting-large")

    standalone_counts = []
    for label, user_ids in (("small", small_users), ("large", large_users)):
        query_count, body = _select_count(
            engine,
            lambda label=label, user_ids=user_ids: authenticated_client.post(
                f"/api/projects/{project['id']}/meetings",
                json=_meeting_payload(user_ids, f"Meeting {label}"),
            ),
            expected_status=201,
        )
        assert len(body["participants"]) == len(user_ids)
        standalone_counts.append(query_count)

    occurrence_counts = []
    for label, user_ids in (("small", small_users), ("large", large_users)):
        series = authenticated_client.post(
            f"/api/projects/{project['id']}/meeting-series",
            json=_series_payload(user_ids, f"Occurrence source {label}"),
        ).json()
        query_count, body = _select_count(
            engine,
            lambda series=series: authenticated_client.post(
                f"/api/meeting-series/{series['id']}/occurrences",
                json={
                    "title": f"Occurrence {label}",
                    "scheduled_start": START.isoformat(),
                    "scheduled_end": (START + timedelta(hours=1)).isoformat(),
                },
            ),
            expected_status=201,
        )
        assert len(body["participants"]) == len(user_ids)
        assert len(body["agenda_items"]) == len(user_ids)
        occurrence_counts.append(query_count)

    assert max(standalone_counts) <= 13
    assert max(standalone_counts) - min(standalone_counts) <= 1
    assert max(occurrence_counts) <= 15
    assert max(occurrence_counts) - min(occurrence_counts) <= 1


def _add_outcome_shape(client, meeting_id: str, user_ids: list[str]) -> None:
    with client.app.state.database.session() as session:
        meeting = session.scalar(select(Meeting).where(Meeting.id == meeting_id))
        admin = session.scalar(select(User).where(User.username == "admin"))
        agenda_items = sorted(meeting.agenda_items, key=lambda item: item.position)
        for index, (agenda, user_id) in enumerate(
            zip(agenda_items, user_ids, strict=True)
        ):
            decision = Decision(
                project_id=meeting.project_id,
                meeting_id=meeting.id,
                agenda_item_id=agenda.id,
                title=f"Decision {index}",
                decision_markdown="Decision",
                created_by=admin.id,
                reviewers=[DecisionReviewer(user_id=user_id)],
            )
            session.add_all(
                [
                    decision,
                    ActionItem(
                        project_id=meeting.project_id,
                        meeting_id=meeting.id,
                        agenda_item_id=agenda.id,
                        content=f"Action {index}",
                        owner_user_id=user_id,
                        created_by=admin.id,
                    ),
                    OpenQuestion(
                        project_id=meeting.project_id,
                        meeting_id=meeting.id,
                        agenda_item_id=agenda.id,
                        question_markdown=f"Question {index}",
                        owner_user_id=user_id,
                        created_by=admin.id,
                    ),
                ]
            )
        session.commit()


def test_meeting_update_and_lifecycle_responses_are_bounded_for_full_shape(
    authenticated_client, project
):
    engine = authenticated_client.app.state.database.engine
    mutation_counts: dict[str, list[int]] = {"update": [], "ready": [], "start": []}

    for label, amount in (("small", 1), ("large", 16)):
        user_ids = _create_users(authenticated_client, amount, f"full-{label}")
        series = authenticated_client.post(
            f"/api/projects/{project['id']}/meeting-series",
            json=_series_payload(user_ids, f"Full source {label}"),
        ).json()
        meeting = authenticated_client.post(
            f"/api/meeting-series/{series['id']}/occurrences",
            json={
                "title": f"Full meeting {label}",
                "scheduled_start": START.isoformat(),
                "scheduled_end": (START + timedelta(hours=1)).isoformat(),
            },
        ).json()
        _add_outcome_shape(authenticated_client, meeting["id"], user_ids)

        query_count, meeting = _select_count(
            engine,
            lambda meeting=meeting: authenticated_client.put(
                f"/api/meetings/{meeting['id']}",
                json={
                    "expected_version": meeting["version"],
                    "title": f"Updated full {label}",
                },
            ),
        )
        assert len(meeting["agenda_items"]) == amount
        assert sum(len(item["decisions"]) for item in meeting["agenda_items"]) == amount
        mutation_counts["update"].append(query_count)

        for operation in ("ready", "start"):
            query_count, meeting = _select_count(
                engine,
                lambda operation=operation, meeting=meeting: authenticated_client.post(
                    f"/api/meetings/{meeting['id']}/{operation}",
                    json={"expected_version": meeting["version"]},
                ),
            )
            mutation_counts[operation].append(query_count)

    for operation, counts in mutation_counts.items():
        assert max(counts) <= 15, (operation, counts)
        assert max(counts) - min(counts) <= 1, (operation, counts)
