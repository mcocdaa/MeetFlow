from datetime import datetime, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole, UserStatus
from app.config import Settings


class AuthService:
    cookie_name = "meetflow_session"
    cookie_max_age = 7 * 24 * 60 * 60

    def __init__(self, settings: Settings):
        self.settings = settings
        self.passwords = PasswordHash.recommended()
        self.signer = URLSafeTimedSerializer(
            settings.app_secret_key, salt="meetflow-session-v1"
        )

    @staticmethod
    def normalize_username(value: str) -> str:
        return value.strip().casefold()

    def bootstrap_admin(self, session: Session) -> User:
        username = self.normalize_username(self.settings.admin_username)
        existing = session.scalar(select(User).where(User.username == username))
        if existing:
            return existing

        admin = User(
            username=username,
            display_name=self.settings.admin_username.strip(),
            password_hash=self.passwords.hash(self.settings.admin_password),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            approved_at=datetime.now(timezone.utc),
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        admin.approved_by = admin.id
        session.commit()
        session.refresh(admin)
        return admin

    def verify_password(self, password: str, password_hash: str) -> bool:
        return self.passwords.verify(password, password_hash)

    def issue_cookie(self, user: User) -> str:
        return self.signer.dumps({"uid": user.id, "sv": user.session_version})

    def read_cookie(self, value: str) -> tuple[str, int] | None:
        try:
            payload = self.signer.loads(value, max_age=self.cookie_max_age)
        except (BadSignature, SignatureExpired, TypeError):
            return None
        if not isinstance(payload, dict) or "uid" not in payload or "sv" not in payload:
            return None
        return str(payload["uid"]), int(payload["sv"])

    def transition_user(
        self,
        session: Session,
        user: User,
        status: UserStatus,
        actor: User,
    ) -> User:
        user.status = status
        if status == UserStatus.ACTIVE:
            user.approved_by = actor.id
            user.approved_at = datetime.now(timezone.utc)
        if status == UserStatus.DISABLED:
            user.session_version += 1
        session.commit()
        session.refresh(user)
        return user
