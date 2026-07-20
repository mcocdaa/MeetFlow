from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User
from app.database import get_session
from app.projects.schemas import ProjectEdit, ProjectUpdateWrite, ProjectWrite
from app.projects.service import ProjectService


router = APIRouter(prefix="/api/projects", tags=["projects"])
updates_router = APIRouter(prefix="/api/project-updates", tags=["projects"])


@router.get("")
def list_projects(
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return ProjectService(session).list()


@router.post("", status_code=201)
def create_project(
    payload: ProjectWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = ProjectService(session)
    return service.serialize(service.create(payload, user))


@router.get("/{project_id}")
def get_project(
    project_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = ProjectService(session)
    return service.serialize(service.require(project_id))


@router.put("/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectEdit,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = ProjectService(session)
    return service.serialize(service.update(project_id, payload, user))


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    ProjectService(session).delete(project_id, user)


@router.get("/{project_id}/updates")
def list_project_updates(
    project_id: str,
    _user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    service = ProjectService(session)
    project = service.require(project_id)
    return [service.serialize_update(update) for update in project.updates]


@router.post("/{project_id}/updates", status_code=201)
def create_project_update(
    project_id: str,
    payload: ProjectUpdateWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = ProjectService(session)
    return service.serialize_update(
        service.create_update(project_id, payload, user)
    )


@updates_router.put("/{update_id}")
def edit_project_update(
    update_id: str,
    payload: ProjectUpdateWrite,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = ProjectService(session)
    return service.serialize_update(service.edit_update(update_id, payload, user))
