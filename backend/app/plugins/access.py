from sqlalchemy.orm import Session

from app.agendas.models import AgendaItem
from app.auth.models import User
from app.errors import AppError
from app.projects.access import WorkspaceAccess


def require_plugin_target_access(
    session: Session,
    target_type: str,
    target_id: str,
    user: User,
    *,
    contribute: bool,
    invalid_message: str = "插件任务目标无效",
) -> None:
    """Require view (or contribution) rights on a plugin job target."""
    access = WorkspaceAccess(session)
    require_project = (
        access.require_project_contribute
        if contribute
        else access.require_project_view
    )
    if target_type == "meeting":
        meeting = access.require_meeting_view(target_id, user)
        require_project(meeting.project_id, user)
        return
    if target_type == "agenda_item":
        agenda_item = session.get(AgendaItem, target_id)
        if agenda_item is None:
            raise AppError(404, "agenda_item_not_found", "议题不存在")
        meeting = access.require_meeting_view(agenda_item.meeting_id, user)
        require_project(meeting.project_id, user)
        return
    if target_type == "project":
        require_project(target_id, user)
        return
    raise AppError(422, "invalid_plugin_target", invalid_message)
