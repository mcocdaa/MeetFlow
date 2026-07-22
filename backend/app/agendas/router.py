from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agendas.schemas import (
    AgendaCommand,
    AgendaEdit,
    AgendaMove,
    AgendaReorder,
    AgendaWrite,
)
from app.agendas.service import AgendaService
from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session

router = APIRouter(tags=["agendas"])


@router.post("/api/meetings/{meeting_id}/agenda-items", status_code=201)
def create_agenda_item(
    meeting_id: str,
    payload: AgendaWrite,
    expected_meeting_version: int = Query(ge=1),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AgendaService(session)
    return service.detail(
        service.create(
            meeting_id,
            payload,
            user,
            expected_meeting_version=expected_meeting_version,
        ).id
    )


@router.put("/api/agenda-items/{item_id}")
def update_agenda_item(
    item_id: str,
    payload: AgendaEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AgendaService(session)
    return service.detail(service.update(item_id, payload, user).id)


@router.delete("/api/agenda-items/{item_id}", status_code=204)
def delete_agenda_item(
    item_id: str,
    payload: AgendaCommand,
    expected_meeting_version: int = Query(ge=1),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    AgendaService(session).delete(
        item_id,
        payload,
        user,
        expected_meeting_version=expected_meeting_version,
    )


@router.post("/api/meetings/{meeting_id}/agenda-items/reorder")
def reorder_agenda_items(
    meeting_id: str,
    payload: AgendaReorder,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    service = AgendaService(session)
    service.reorder(meeting_id, payload, user)
    return service.ordered_detail(meeting_id)


def _command(name: str):
    def run(
        item_id: str,
        payload: AgendaCommand,
        user: User = Depends(current_user),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        service = AgendaService(session)
        item = getattr(service, name)(item_id, payload, user)
        return service.detail(item.id)

    return run


router.add_api_route(
    "/api/agenda-items/{item_id}/start", _command("start"), methods=["POST"]
)
router.add_api_route(
    "/api/agenda-items/{item_id}/complete",
    _command("complete"),
    methods=["POST"],
)
router.add_api_route(
    "/api/agenda-items/{item_id}/skip", _command("skip"), methods=["POST"]
)
router.add_api_route(
    "/api/agenda-items/{item_id}/cancel", _command("cancel"), methods=["POST"]
)


@router.post("/api/agenda-items/{item_id}/move")
def move_agenda_item(
    item_id: str,
    payload: AgendaMove,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AgendaService(session)
    return service.detail(service.move(item_id, payload, user).id)
