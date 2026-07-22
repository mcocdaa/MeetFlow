from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import admin_user, current_user
from app.auth.models import User, UserRole, UserStatus
from app.auth.schemas import (
    AdminCreateUserRequest,
    LoginRequest,
    PasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)
from app.database import get_session
from app.errors import AppError

router = APIRouter(prefix="/api/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/admin/users", tags=["admin/users"])


def public_user(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        avatar_color=user.avatar_color,
        role=user.role.value,
        status=user.status.value,
    )


@router.get("/config")
def auth_config(request: Request) -> dict[str, bool]:
    return {"allow_registration": request.app.state.settings.allow_registration}


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> UserResponse:
    service = request.app.state.auth_service
    user = session.scalar(
        select(User).where(
            User.username == service.normalize_username(payload.username)
        )
    )
    if not user or not service.verify_password(
        payload.password, user.password_hash
    ):
        raise AppError(401, "invalid_credentials", "用户名或密码错误")
    if user.status != UserStatus.ACTIVE:
        messages = {
            UserStatus.PENDING: "账号正在等待管理员批准",
            UserStatus.REJECTED: "账号申请未获批准",
            UserStatus.DISABLED: "账号已被管理员停用",
        }
        raise AppError(
            403, f"account_{user.status.value}", messages[user.status]
        )

    response.set_cookie(
        service.cookie_name,
        service.issue_cookie(user),
        max_age=service.cookie_max_age,
        httponly=True,
        secure=request.app.state.settings.secure_cookies,
        samesite="strict",
    )
    return public_user(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    response.delete_cookie(request.app.state.auth_service.cookie_name)


@router.post("/register", status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    if not request.app.state.settings.allow_registration:
        raise AppError(403, "registration_closed", "当前不开放注册")

    service = request.app.state.auth_service
    user = User(
        username=service.normalize_username(payload.username),
        display_name=payload.display_name.strip(),
        password_hash=service.passwords.hash(payload.password),
        role=UserRole.MEMBER,
        status=UserStatus.PENDING,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "username_taken", "用户名已存在") from exc
    return {"status": "pending"}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> UserResponse:
    return public_user(user)


@router.post("/change-password", status_code=204)
def change_password(
    payload: PasswordRequest,
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    service = request.app.state.auth_service
    if not service.verify_password(
        payload.current_password, user.password_hash
    ):
        raise AppError(400, "wrong_password", "当前密码错误")
    user.password_hash = service.passwords.hash(payload.new_password)
    user.session_version += 1
    session.commit()


def target_user(user_id: str, session: Session) -> User:
    user = session.get(User, user_id)
    if not user:
        raise AppError(404, "user_not_found", "用户不存在")
    return user


@admin_router.get("", response_model=list[UserResponse])
def list_users(
    status: UserStatus | None = None,
    _admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> list[UserResponse]:
    statement = select(User).order_by(User.created_at.desc())
    if status:
        statement = statement.where(User.status == status)
    return [public_user(user) for user in session.scalars(statement)]


@admin_router.post("", status_code=201, response_model=UserResponse)
def create_user(
    payload: AdminCreateUserRequest,
    request: Request,
    admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> UserResponse:
    service = request.app.state.auth_service
    user = User(
        username=service.normalize_username(payload.username),
        display_name=payload.display_name.strip(),
        password_hash=service.passwords.hash(payload.password),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        approved_by=admin.id,
        approved_at=datetime.now(timezone.utc),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(409, "username_taken", "用户名已存在") from exc
    session.refresh(user)
    return public_user(user)


@admin_router.post("/{user_id}/approve", response_model=UserResponse)
def approve(
    user_id: str,
    request: Request,
    admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> UserResponse:
    target = target_user(user_id, session)
    if target.role == UserRole.ADMIN or target.status != UserStatus.PENDING:
        raise AppError(400, "invalid_user_transition", "只能批准待审批成员")
    user = request.app.state.auth_service.transition_user(
        session, target, UserStatus.ACTIVE, admin
    )
    return public_user(user)


@admin_router.post("/{user_id}/reject", response_model=UserResponse)
def reject(
    user_id: str,
    request: Request,
    admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> UserResponse:
    target = target_user(user_id, session)
    if target.role == UserRole.ADMIN:
        raise AppError(400, "cannot_modify_admin", "不能拒绝管理员账号")
    if target.status != UserStatus.PENDING:
        raise AppError(400, "invalid_user_transition", "只能拒绝待审批成员")
    user = request.app.state.auth_service.transition_user(
        session, target, UserStatus.REJECTED, admin
    )
    return public_user(user)


@admin_router.post("/{user_id}/disable", response_model=UserResponse)
def disable(
    user_id: str,
    request: Request,
    admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> UserResponse:
    user = target_user(user_id, session)
    if user.id == admin.id:
        raise AppError(400, "cannot_disable_self", "不能禁用当前管理员")
    user = request.app.state.auth_service.transition_user(
        session, user, UserStatus.DISABLED, admin
    )
    return public_user(user)


@admin_router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: str,
    payload: ResetPasswordRequest,
    request: Request,
    _admin: User = Depends(admin_user),
    session: Session = Depends(get_session),
) -> None:
    user = target_user(user_id, session)
    user.password_hash = request.app.state.auth_service.passwords.hash(
        payload.password
    )
    user.session_version += 1
    session.commit()
