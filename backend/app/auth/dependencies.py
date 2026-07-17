from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole, UserStatus
from app.database import get_session
from app.errors import AppError


def current_user(
    request: Request, session: Session = Depends(get_session)
) -> User:
    value = request.cookies.get(request.app.state.auth_service.cookie_name)
    parsed = request.app.state.auth_service.read_cookie(value) if value else None
    if not parsed:
        raise AppError(401, "not_authenticated", "请先登录")

    user_id, session_version = parsed
    user = session.get(User, user_id)
    if (
        not user
        or user.status != UserStatus.ACTIVE
        or user.session_version != session_version
    ):
        raise AppError(401, "session_invalid", "登录状态已失效")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise AppError(403, "admin_required", "需要管理员权限")
    return user
