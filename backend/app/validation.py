from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserStatus
from app.errors import AppError


def require_active(actor: User) -> None:
    if actor.status != UserStatus.ACTIVE:
        raise AppError(403, "active_user_required", "账号尚未启用")


def fetch_users(
    session: Session,
    user_ids: Iterable[str | None],
    *,
    message: str,
    check_active: bool = False,
) -> dict[str, User]:
    ids = list(dict.fromkeys(value for value in user_ids if value))
    if not ids:
        return {}
    users = {
        user.id: user
        for user in session.scalars(select(User).where(User.id.in_(ids)))
    }
    invalid = [user_id for user_id in ids if user_id not in users]
    if check_active:
        invalid += [
            user_id
            for user_id in ids
            if user_id in users and users[user_id].status != UserStatus.ACTIVE
        ]
    if invalid:
        raise AppError(
            422,
            "user_not_found",
            message,
            details={"user_ids": invalid},
        )
    return users
