from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole, UserStatus
from app.database import get_session
from app.errors import AppError


def optional_current_user(
    request: Request, session: Session = Depends(get_session)
) -> User | None:
    service = request.app.state.auth_service

    api_key = request.headers.get("x-api-key")
    if not api_key:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            bearer_token = auth_header[7:].strip()
            if bearer_token.startswith("mf_"):
                api_key = bearer_token
            elif bearer_token:
                parsed_cookie = service.read_cookie(bearer_token)
                if not parsed_cookie:
                    return None
                user_id, session_version = parsed_cookie
                user = session.get(User, user_id)
                if (
                    not user
                    or user.status != UserStatus.ACTIVE
                    or user.session_version != session_version
                ):
                    return None
                return user

    if api_key is not None:
        parsed_key = service.parse_api_key(api_key)
        if not parsed_key:
            return None
        user_id, normalized_key = parsed_key
        user = session.get(User, user_id)
        if (
            not user
            or user.status != UserStatus.ACTIVE
            or not service.verify_api_key(normalized_key, user)
        ):
            return None
        return user

    value = request.cookies.get(service.cookie_name)
    parsed = service.read_cookie(value) if value else None
    if not parsed:
        return None

    user_id, session_version = parsed
    user = session.get(User, user_id)
    if (
        not user
        or user.status != UserStatus.ACTIVE
        or user.session_version != session_version
    ):
        return None
    return user


def current_user(
    user: User | None = Depends(optional_current_user),
) -> User:
    if not user:
        raise AppError(401, "not_authenticated", "请先登录")
    return user


get_current_user = current_user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise AppError(403, "admin_required", "需要管理员权限")
    return user
