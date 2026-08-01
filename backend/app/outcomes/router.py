from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.outcomes.schemas import (
    ActionEdit,
    ActionWrite,
    AgendaCopyWrite,
    AgendaConvertWrite,
    AgendaOutcomeMigrationWrite,
    DecisionEdit,
    DecisionFinalizeWrite,
    DecisionReviewWrite,
    DecisionSupersedeWrite,
    DecisionWrite,
    QuestionEdit,
    QuestionResolveWrite,
    QuestionScheduleWrite,
    QuestionWrite,
)
from app.outcomes.service import OutcomeService

router = APIRouter(tags=["outcomes"])


def _service(session: Session) -> OutcomeService:
    return OutcomeService(session)


@router.get("/api/projects/{project_id}/decisions")
def list_decisions(
    project_id: str,
    limit: int = Query(default=200, ge=1, le=200),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    service = _service(session)
    return [
        service.serialize(item)
        for item in service.list_decisions(project_id, limit, actor=user)
    ]


@router.post("/api/projects/{project_id}/decisions", status_code=201)
def create_decision(
    project_id: str,
    payload: DecisionWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.create_decision(project_id, payload, user))


@router.put("/api/decisions/{decision_id}")
def update_decision(
    decision_id: str,
    payload: DecisionEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.update_decision(decision_id, payload, user))


@router.post("/api/decisions/{decision_id}/review")
def review_decision(
    decision_id: str,
    payload: DecisionReviewWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.review_decision(decision_id, payload, user))


@router.post("/api/decisions/{decision_id}/finalize")
def finalize_decision(
    decision_id: str,
    payload: DecisionFinalizeWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.finalize_decision(decision_id, payload, user))


@router.post("/api/decisions/{decision_id}/withdraw")
def withdraw_decision(
    decision_id: str,
    payload: DecisionFinalizeWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.withdraw_decision(decision_id, payload, user))


@router.post("/api/decisions/{decision_id}/supersede")
def supersede_decision(
    decision_id: str,
    payload: DecisionSupersedeWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.supersede_decision(decision_id, payload, user))


@router.get("/api/projects/{project_id}/actions")
def list_actions(
    project_id: str,
    limit: int = Query(default=200, ge=1, le=200),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    service = _service(session)
    return [
        service.serialize(item)
        for item in service.list_actions(project_id, limit, actor=user)
    ]


@router.post("/api/projects/{project_id}/actions", status_code=201)
def create_action(
    project_id: str,
    payload: ActionWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.create_action(project_id, payload, user))


@router.put("/api/actions/{action_id}")
def update_action(
    action_id: str,
    payload: ActionEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.update_action(action_id, payload, user))


@router.get("/api/projects/{project_id}/open-questions")
def list_questions(
    project_id: str,
    limit: int = Query(default=200, ge=1, le=200),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    service = _service(session)
    return [
        service.serialize(item)
        for item in service.list_questions(project_id, limit, actor=user)
    ]


@router.post("/api/projects/{project_id}/open-questions", status_code=201)
def create_question(
    project_id: str,
    payload: QuestionWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.create_question(project_id, payload, user))


@router.put("/api/open-questions/{question_id}")
def update_question(
    question_id: str,
    payload: QuestionEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.update_question(question_id, payload, user))


@router.post("/api/open-questions/{question_id}/schedule", status_code=201)
def schedule_question(
    question_id: str,
    payload: QuestionScheduleWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    item = service.schedule_question(question_id, payload, user)
    return {
        column.name: getattr(item, column.name) for column in item.__table__.columns
    }


@router.post("/api/open-questions/{question_id}/resolve")
def resolve_question(
    question_id: str,
    payload: QuestionResolveWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.resolve_question(question_id, payload, user))


@router.post("/api/agenda-items/{item_id}/migrate-outcomes")
def migrate_outcomes(
    item_id: str,
    payload: AgendaOutcomeMigrationWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = _service(session).migrate_agenda_outcomes(item_id, payload, user)
    return {
        column.name: getattr(item, column.name) for column in item.__table__.columns
    }


@router.post("/api/agenda-items/{item_id}/convert-to-question", status_code=201)
def convert_to_question(
    item_id: str,
    payload: AgendaConvertWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = _service(session)
    return service.serialize(service.convert_agenda_to_question(item_id, payload, user))


@router.post("/api/agenda-items/{item_id}/copy-to-meeting", status_code=201)
def copy_to_meeting(
    item_id: str,
    payload: AgendaCopyWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = _service(session).copy_agenda_to_meeting(item_id, payload, user)
    return {
        column.name: getattr(item, column.name) for column in item.__table__.columns
    }
