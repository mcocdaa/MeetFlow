# MeetFlow MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and Docker-deploy a lightweight shared meeting archive with approved-user access, structured meeting packages, attachments, action tracking, and a restart-loaded Python plugin contract.

**Architecture:** A Vue 3 SPA and FastAPI API ship in one production container. FastAPI owns authentication, SQLite persistence, local attachment storage, and a manifest-driven trusted-plugin registry; `/app/data` is writable and persistent while `/app/plugins` is a read-only extension mount.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, SQLite, Pydantic Settings, pwdlib/Argon2, itsdangerous, cryptography, Vue 3, TypeScript, Vite, Vue Router, Vitest, pytest, Docker.

---

## Scope and delivery order

The approved design contains three coupled subsystems. Keep one plan because they share the same user model, HTTP client, application factory, database, and Docker artifact, but execute them as independently testable stages:

1. Foundation and authentication.
2. Meeting archive and collaboration workflow.
3. Plugin contract and production deployment.

The first usable checkpoint is the authenticated shared shell after Task 5. The second is the complete meeting workflow after Task 10. The final checkpoint adds the plugin extension boundary and single-container deployment.

## File map

```text
MeetFlow/
├── .env.example                         # Safe configuration template
├── .gitignore                           # Local secrets, data and build artifacts
├── Dockerfile                           # Multi-stage Vue + FastAPI image
├── docker-compose.yml                   # Data and read-only plugin mounts
├── pyproject.toml                       # Python dependencies and pytest config
├── README.md                            # Local and remote deployment guide
├── scripts/
│   └── start.sh                         # Only supported local/Docker start entrypoint
├── backend/
│   ├── app/
│   │   ├── main.py                      # Application factory and static fallback
│   │   ├── config.py                    # Environment validation
│   │   ├── database.py                  # Engine/session ownership and schema init
│   │   ├── errors.py                    # Uniform API error envelope
│   │   ├── auth/
│   │   │   ├── models.py                # User persistence model and enums
│   │   │   ├── schemas.py               # Auth/admin request and response models
│   │   │   ├── service.py               # Passwords, cookies and account transitions
│   │   │   ├── dependencies.py          # Current-user/admin dependencies
│   │   │   └── router.py                # Auth and admin user endpoints
│   │   ├── meetings/
│   │   │   ├── models.py                # Meeting, action, attachment and update rows
│   │   │   ├── schemas.py               # Meeting-package API contracts
│   │   │   ├── service.py               # CRUD, attribution and cascade workflows
│   │   │   └── router.py                # Meeting/action/update endpoints
│   │   ├── attachments/
│   │   │   ├── storage.py               # Safe paths and atomic file operations
│   │   │   └── router.py                # Upload/download/delete endpoints
│   │   └── plugins/
│   │       ├── contracts.py              # Manifest and meeting-action protocol
│   │       ├── models.py                 # Enabled state and encrypted config rows
│   │       ├── secrets.py                # Derived-key encryption
│   │       ├── manager.py                # Discovery, load and failure isolation
│   │       └── router.py                 # Admin config and generic action endpoints
│   └── tests/
│       ├── conftest.py                   # Isolated app/data/plugin fixtures
│       ├── test_health.py
│       ├── auth/
│       │   ├── test_bootstrap.py
│       │   ├── test_auth_api.py
│       │   └── test_admin_users.py
│       ├── meetings/
│       │   ├── test_meetings_api.py
│       │   ├── test_actions_updates.py
│       │   └── test_attachments.py
│       └── plugins/
│           ├── test_discovery.py
│           ├── test_config.py
│           └── test_actions.py
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── router.ts
│       ├── styles.css
│       ├── api/client.ts                 # Credentials and error envelope handling
│       ├── auth/session.ts               # Reactive current-user state
│       ├── components/
│       │   ├── MarkdownView.vue
│       │   ├── MeetingCard.vue
│       │   ├── ActionItemEditor.vue
│       │   ├── AttachmentPanel.vue
│       │   └── PluginActionPanel.vue
│       ├── views/
│       │   ├── LoginView.vue
│       │   ├── RegisterView.vue
│       │   ├── WorkspaceView.vue
│       │   ├── AccountView.vue
│       │   ├── MeetingsView.vue
│       │   ├── MeetingDetailView.vue
│       │   ├── OpenActionsView.vue
│       │   ├── AdminUsersView.vue
│       │   └── AdminPluginsView.vue
│       └── tests/
│           ├── setup.ts
│           ├── auth.test.ts
│           ├── meetings.test.ts
│           └── plugin-actions.test.ts
└── plugins/
    └── plugins.yaml                      # Empty production registry with documented shape
```

## Stage 1: Foundation and authentication

### Task 1: Backend application factory and health endpoint

**Files:**
- Create: `pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/app/errors.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Define dependencies and pytest import configuration**

```toml
# pyproject.toml
[project]
name = "meetflow"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115,<1",
  "uvicorn[standard]>=0.34,<1",
  "sqlalchemy>=2.0,<3",
  "pydantic-settings>=2.7,<3",
  "pwdlib[argon2]>=0.2,<1",
  "itsdangerous>=2.2,<3",
  "cryptography>=44,<46",
  "jsonschema>=4.23,<5",
  "python-multipart>=0.0.20,<1",
  "PyYAML>=6,<7",
]

[project.optional-dependencies]
test = ["pytest>=8,<9", "httpx>=0.28,<1"]

[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["backend"]

[tool.pytest.ini_options]
pythonpath = ["backend"]
testpaths = ["backend/tests"]
```

- [ ] **Step 2: Create the Python environment**

Run: `python -m venv .venv && .venv/bin/python -m pip install -e '.[test]'`

Expected: MeetFlow and all backend test dependencies install successfully.

- [ ] **Step 3: Write the failing health test**

```python
# backend/tests/test_health.py
def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Add an isolated application fixture**

```python
# backend/tests/conftest.py
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "data",
        plugins_dir=tmp_path / "plugins",
        admin_username="admin",
        admin_password="correct-horse-battery",
        app_secret_key="test-secret-key-with-at-least-32-chars",
        allow_registration=True,
        secure_cookies=False,
    )


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
```

- [ ] **Step 5: Run the test to verify the application is missing**

Run: `.venv/bin/python -m pytest backend/tests/test_health.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 6: Implement validated settings and the database owner**

```python
# backend/app/config.py
from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./data/meetflow.db"
    data_dir: Path = Path("data")
    plugins_dir: Path = Path("plugins")
    admin_username: str = "admin"
    admin_password: str = "development-admin-password"
    app_secret_key: str = "development-secret-key-32-characters"
    allow_registration: bool = True
    secure_cookies: bool = False
    trusted_origins: str = "http://localhost:8000,http://localhost:5173"
    max_upload_bytes: int = 20 * 1024 * 1024

    @property
    def trusted_origin_set(self) -> set[str]:
        return {item.strip().rstrip("/") for item in self.trusted_origins.split(",") if item.strip()}

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.app_env == "production":
            if len(self.admin_password) < 12 or self.admin_password == "development-admin-password":
                raise ValueError("ADMIN_PASSWORD must contain at least 12 characters")
            if len(self.app_secret_key) < 32 or self.app_secret_key == "development-secret-key-32-characters":
                raise ValueError("APP_SECRET_KEY must contain at least 32 characters")
        return self
```

```python
# backend/app/database.py
from sqlalchemy import create_engine, event
from fastapi import Request
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        )
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._configure_sqlite)

    @staticmethod
    def _configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return Session(self.engine)


def get_session(request: Request):
    with request.app.state.database.session() as session:
        yield session
```

- [ ] **Step 7: Add the uniform error model and app factory**

```python
# backend/app/errors.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
```

```python
# backend/app/main.py
from fastapi import FastAPI, Request

from app.config import Settings
from app.database import Database
from app.errors import install_error_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    database = Database(resolved.database_url)

    app = FastAPI(title="MeetFlow", version="0.1.0")
    app.state.settings = resolved
    app.state.database = database
    install_error_handlers(app)

    @app.middleware("http")
    async def reject_cross_origin_writes(request, call_next):
        origin = request.headers.get("origin", "").rstrip("/")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin and origin not in resolved.trusted_origin_set:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"error": {"code": "origin_forbidden", "message": "请求来源不受信任"}})
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.on_event("startup")
    def startup():
        resolved.data_dir.mkdir(parents=True, exist_ok=True)
        resolved.plugins_dir.mkdir(parents=True, exist_ok=True)
        database.create_schema()

    return app
app = create_app()
```

- [ ] **Step 8: Run the health test**

Run: `.venv/bin/python -m pytest backend/tests/test_health.py -q`

Expected: `1 passed`.

- [ ] **Step 9: Commit the foundation**

```bash
git add pyproject.toml backend
git commit -m "feat: add FastAPI application foundation"
```

### Task 2: User model, administrator bootstrap, and cookie service

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/models.py`
- Create: `backend/app/auth/service.py`
- Create: `backend/tests/auth/test_bootstrap.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Test administrator creation and idempotence**

```python
# backend/tests/auth/test_bootstrap.py
from sqlalchemy import select

from app.auth.models import User, UserRole, UserStatus
from app.auth.service import AuthService


def test_bootstrap_creates_one_active_admin(settings, client):
    with client.app.state.database.session() as session:
        service = AuthService(settings)
        service.bootstrap_admin(session)
        service.bootstrap_admin(session)
        users = session.scalars(select(User)).all()

    assert len(users) == 1
    assert users[0].username == "admin"
    assert users[0].role == UserRole.ADMIN
    assert users[0].status == UserStatus.ACTIVE
    assert users[0].password_hash != settings.admin_password
```

- [ ] **Step 2: Run the test and confirm the missing model**

Run: `.venv/bin/python -m pytest backend/tests/auth/test_bootstrap.py -q`

Expected: collection fails because `app.auth.models` does not exist.

- [ ] **Step 3: Create the user model**

```python
# backend/app/auth/models.py
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"


class UserStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    DISABLED = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Implement passwords, bootstrap, and signed cookies**

```python
# backend/app/auth/service.py
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
        self.signer = URLSafeTimedSerializer(settings.app_secret_key, salt="meetflow-session-v1")

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
        return admin

    def verify_password(self, password: str, password_hash: str) -> bool:
        return self.passwords.verify(password, password_hash)

    def issue_cookie(self, user: User) -> str:
        return self.signer.dumps({"uid": user.id, "sv": user.session_version})

    def read_cookie(self, value: str) -> tuple[str, int] | None:
        try:
            payload = self.signer.loads(value, max_age=self.cookie_max_age)
        except (BadSignature, SignatureExpired):
            return None
        return str(payload["uid"]), int(payload["sv"])
```

- [ ] **Step 5: Import models before schema creation and bootstrap on startup**

```python
# backend/app/main.py additions inside create_app; replace the Task 1 startup handler
from app.auth.models import User
from app.auth.service import AuthService

auth_service = AuthService(resolved)
app.state.auth_service = auth_service

@app.on_event("startup")
def startup():
    resolved.data_dir.mkdir(parents=True, exist_ok=True)
    resolved.plugins_dir.mkdir(parents=True, exist_ok=True)
    database.create_schema()
    with database.session() as session:
        auth_service.bootstrap_admin(session)
```

- [ ] **Step 6: Run the focused test, then all backend tests**

Run: `.venv/bin/python -m pytest backend/tests/auth/test_bootstrap.py -q`

Expected: `1 passed`.

Run: `.venv/bin/python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 7: Commit the identity foundation**

```bash
git add backend/app/auth backend/app/main.py backend/tests/auth
git commit -m "feat: bootstrap administrator identity"
```

### Task 3: Authentication and registration API

**Files:**
- Create: `backend/app/auth/schemas.py`
- Create: `backend/app/auth/dependencies.py`
- Create: `backend/app/auth/router.py`
- Create: `backend/tests/auth/test_auth_api.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write API tests for login and pending registration**

```python
# backend/tests/auth/test_auth_api.py
def test_admin_can_login_and_read_session(client):
    login = client.post("/api/auth/login", json={"username": "ADMIN", "password": "correct-horse-battery"})
    assert login.status_code == 200
    assert login.json()["role"] == "admin"
    assert client.get("/api/auth/me").json()["username"] == "admin"


def test_registration_creates_pending_user_without_logging_in(client):
    response = client.post(
        "/api/auth/register",
        json={"username": "Alice", "display_name": "Alice", "password": "a-secure-member-pass"},
    )
    assert response.status_code == 201
    assert response.json() == {"status": "pending"}
    assert client.get("/api/auth/me").status_code == 401


def test_cross_origin_write_is_rejected(client):
    response = client.post(
        "/api/auth/login",
        headers={"Origin": "https://evil.example"},
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_forbidden"


def test_closed_registration_is_advertised_and_rejected(client, settings):
    settings.allow_registration = False
    assert client.get("/api/auth/config").json() == {"allow_registration": False}
    response = client.post(
        "/api/auth/register",
        json={"username": "alice", "display_name": "Alice", "password": "a-secure-member-pass"},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests and verify 404 responses**

Run: `.venv/bin/python -m pytest backend/tests/auth/test_auth_api.py -q`

Expected: both tests fail because the auth routes are absent.

- [ ] **Step 3: Define request and safe response schemas**

```python
# backend/app/auth/schemas.py
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=200)


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    status: str


class PasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)
```

- [ ] **Step 4: Implement current-user and administrator dependencies**

```python
# backend/app/auth/dependencies.py
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole, UserStatus
from app.errors import AppError
from app.database import get_session


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    value = request.cookies.get(request.app.state.auth_service.cookie_name)
    parsed = request.app.state.auth_service.read_cookie(value) if value else None
    if not parsed:
        raise AppError(401, "not_authenticated", "请先登录")
    user_id, session_version = parsed
    user = session.get(User, user_id)
    if not user or user.status != UserStatus.ACTIVE or user.session_version != session_version:
        raise AppError(401, "session_invalid", "登录状态已失效")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise AppError(403, "admin_required", "需要管理员权限")
    return user
```

- [ ] **Step 5: Implement login, logout, registration, current user, and password change**

```python
# backend/app/auth/router.py
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import current_user
from app.auth.models import User, UserRole, UserStatus
from app.auth.schemas import LoginRequest, PasswordRequest, RegisterRequest, UserResponse
from app.errors import AppError
from app.database import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


def public_user(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role.value,
        status=user.status.value,
    )


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    service = request.app.state.auth_service
    user = session.scalar(select(User).where(User.username == service.normalize_username(payload.username)))
    if not user or not service.verify_password(payload.password, user.password_hash):
        raise AppError(401, "invalid_credentials", "用户名或密码错误")
    if user.status != UserStatus.ACTIVE:
        messages = {
            UserStatus.PENDING: "账号正在等待管理员批准",
            UserStatus.REJECTED: "账号申请未获批准",
            UserStatus.DISABLED: "账号已被管理员停用",
        }
        raise AppError(403, f"account_{user.status.value}", messages[user.status])
    response.set_cookie(
        service.cookie_name,
        service.issue_cookie(user),
        max_age=service.cookie_max_age,
        httponly=True,
        secure=request.app.state.settings.secure_cookies,
        samesite="strict",
    )
    return public_user(user)


@router.get("/config")
def auth_config(request: Request):
    return {"allow_registration": request.app.state.settings.allow_registration}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    response.delete_cookie(request.app.state.auth_service.cookie_name)


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, request: Request, session: Session = Depends(get_session)):
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
    except IntegrityError:
        session.rollback()
        raise AppError(409, "username_taken", "用户名已存在")
    return {"status": "pending"}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return public_user(user)


@router.post("/change-password", status_code=204)
def change_password(payload: PasswordRequest, request: Request, user: User = Depends(current_user), session: Session = Depends(get_session)):
    service = request.app.state.auth_service
    if not service.verify_password(payload.current_password, user.password_hash):
        raise AppError(400, "wrong_password", "当前密码错误")
    user.password_hash = service.passwords.hash(payload.new_password)
    user.session_version += 1
    session.commit()
```

- [ ] **Step 6: Register the router**

```python
# backend/app/main.py inside create_app, after app construction
from app.auth.router import router as auth_router
app.include_router(auth_router)
```

- [ ] **Step 7: Run auth tests**

Run: `.venv/bin/python -m pytest backend/tests/auth -q`

Expected: all auth tests pass.

- [ ] **Step 8: Commit authentication routes**

```bash
git add backend/app/auth backend/app/main.py backend/tests/auth
git commit -m "feat: add login and registration workflow"
```

### Task 4: Administrator account approval API

**Files:**
- Modify: `backend/app/auth/schemas.py`
- Modify: `backend/app/auth/router.py`
- Create: `backend/tests/auth/test_admin_users.py`

- [ ] **Step 1: Test approval, fixed-account creation, and authorization**

```python
# backend/tests/auth/test_admin_users.py
def login_admin(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-battery"})
    assert response.status_code == 200


def test_admin_approves_pending_user(client):
    client.post("/api/auth/register", json={"username": "alice", "display_name": "Alice", "password": "a-secure-member-pass"})
    login_admin(client)
    pending = client.get("/api/admin/users?status=pending").json()
    response = client.post(f"/api/admin/users/{pending[0]['id']}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_admin_creates_active_demo_account(client):
    login_admin(client)
    response = client.post(
        "/api/admin/users",
        json={"username": "demo", "display_name": "Demo", "password": "fixed-demo-password"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "active"
```

- [ ] **Step 2: Run the test and verify missing admin routes**

Run: `.venv/bin/python -m pytest backend/tests/auth/test_admin_users.py -q`

Expected: tests fail with 404.

- [ ] **Step 3: Add admin request schema and state-transition helper**

```python
# backend/app/auth/schemas.py
class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=200)


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=12, max_length=200)
```

```python
# backend/app/auth/service.py: add inside AuthService
    def transition_user(self, session: Session, user: User, status: UserStatus, actor: User) -> User:
        user.status = status
        if status == UserStatus.ACTIVE:
            user.approved_by = actor.id
            user.approved_at = datetime.now(timezone.utc)
        if status == UserStatus.DISABLED:
            user.session_version += 1
        session.commit()
        session.refresh(user)
        return user
```

- [ ] **Step 4: Add admin list, create, approve, reject, disable, and reset routes**

```python
# backend/app/auth/router.py additions
from datetime import datetime, timezone
from app.auth.dependencies import admin_user
from app.auth.schemas import AdminCreateUserRequest, ResetPasswordRequest

admin_router = APIRouter(prefix="/api/admin/users", tags=["admin/users"])


@admin_router.get("", response_model=list[UserResponse])
def list_users(status: UserStatus | None = None, _admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    statement = select(User).order_by(User.created_at.desc())
    if status:
        statement = statement.where(User.status == status)
    return [public_user(user) for user in session.scalars(statement)]


@admin_router.post("", status_code=201, response_model=UserResponse)
def create_user(payload: AdminCreateUserRequest, request: Request, _admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    service = request.app.state.auth_service
    user = User(
        username=service.normalize_username(payload.username),
        display_name=payload.display_name.strip(),
        password_hash=service.passwords.hash(payload.password),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        approved_by=_admin.id,
        approved_at=datetime.now(timezone.utc),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AppError(409, "username_taken", "用户名已存在")
    return public_user(user)


def target_user(user_id: str, session: Session) -> User:
    user = session.get(User, user_id)
    if not user:
        raise AppError(404, "user_not_found", "用户不存在")
    return user


@admin_router.post("/{user_id}/approve", response_model=UserResponse)
def approve(user_id: str, request: Request, admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    return public_user(request.app.state.auth_service.transition_user(session, target_user(user_id, session), UserStatus.ACTIVE, admin))


@admin_router.post("/{user_id}/reject", response_model=UserResponse)
def reject(user_id: str, request: Request, admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    return public_user(request.app.state.auth_service.transition_user(session, target_user(user_id, session), UserStatus.REJECTED, admin))


@admin_router.post("/{user_id}/disable", response_model=UserResponse)
def disable(user_id: str, request: Request, admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    user = target_user(user_id, session)
    if user.id == admin.id:
        raise AppError(400, "cannot_disable_self", "不能禁用当前管理员")
    return public_user(request.app.state.auth_service.transition_user(session, user, UserStatus.DISABLED, admin))


@admin_router.post("/{user_id}/reset-password", status_code=204)
def reset_password(user_id: str, payload: ResetPasswordRequest, request: Request, _admin: User = Depends(admin_user), session: Session = Depends(get_session)):
    user = target_user(user_id, session)
    user.password_hash = request.app.state.auth_service.passwords.hash(payload.password)
    user.session_version += 1
    session.commit()
```

- [ ] **Step 5: Include `admin_router` from `backend/app/main.py`**

```python
from app.auth.router import admin_router, router as auth_router
app.include_router(auth_router)
app.include_router(admin_router)
```

- [ ] **Step 6: Run the authorization suite**

Run: `.venv/bin/python -m pytest backend/tests/auth -q`

Expected: all tests pass, including a new assertion that a member receives 403 from `/api/admin/users`.

- [ ] **Step 7: Commit administrator workflows**

```bash
git add backend/app/auth backend/app/main.py backend/tests/auth
git commit -m "feat: add account approval administration"
```

### Task 5: Vue shell, authentication views, and route guards

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/package-lock.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/router.ts`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/auth/session.ts`
- Create: `frontend/src/views/LoginView.vue`
- Create: `frontend/src/views/RegisterView.vue`
- Create: `frontend/src/views/WorkspaceView.vue`
- Create: `frontend/src/views/AccountView.vue`
- Create: `frontend/src/views/AdminUsersView.vue`
- Create: `frontend/src/tests/setup.ts`
- Create: `frontend/src/tests/auth.test.ts`

- [ ] **Step 1: Add Vue, test, Markdown, and sanitization dependencies**

```json
{
  "name": "meetflow-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "vue-tsc -b && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "dompurify": "^3.2.0",
    "marked": "^15.0.0",
    "vue": "^3.5.0",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@testing-library/vue": "^8.1.0",
    "@testing-library/jest-dom": "^6.6.0",
    "@vitejs/plugin-vue": "^5.2.0",
    "@vue/tsconfig": "^0.7.0",
    "jsdom": "^26.0.0",
    "typescript": "^5.7.0",
    "vite": "^6.0.0",
    "vitest": "^3.0.0",
    "vue-tsc": "^2.2.0"
  }
}
```

Run: `cd frontend && npm install`

Expected: dependencies install and `frontend/package-lock.json` is created for reproducible Docker builds.

- [ ] **Step 2: Write a failing login view test**

```ts
// frontend/src/tests/auth.test.ts
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import LoginView from '../views/LoginView.vue'

vi.mock('../api/client', () => ({
  api: vi.fn().mockResolvedValue({ username: 'admin', display_name: 'Admin', role: 'admin', status: 'active' }),
}))

describe('LoginView', () => {
  it('submits credentials and emits success', async () => {
    const { emitted } = render(LoginView)
    await fireEvent.update(screen.getByLabelText('用户名'), 'admin')
    await fireEvent.update(screen.getByLabelText('密码'), 'correct-horse-battery')
    await fireEvent.click(screen.getByRole('button', { name: '登录' }))
    expect(emitted().loggedIn).toHaveLength(1)
  })
})
```

- [ ] **Step 3: Configure TypeScript, Vite proxy, and Vitest**

```json
// frontend/tsconfig.json
{
  "extends": "@vue/tsconfig/tsconfig.dom.json",
  "include": ["src/**/*.ts", "src/**/*.vue", "vite.config.ts"],
  "compilerOptions": { "strict": true, "types": ["vitest/globals"] }
}
```

```html
<!-- frontend/index.html -->
<div id="app"></div>
<script type="module" src="/src/main.ts"></script>
```

```ts
// frontend/vite.config.ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: { environment: 'jsdom', setupFiles: ['./src/tests/setup.ts'] },
})
```

```ts
// frontend/src/tests/setup.ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 4: Implement the typed API error boundary and session store**

```ts
// frontend/src/api/client.ts
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...init, headers, credentials: 'include' })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ error: { code: 'request_failed', message: '请求失败' } }))
    throw new ApiError(response.status, payload.error.code, payload.error.message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
```

```ts
// frontend/src/auth/session.ts
import { reactive } from 'vue'
import { api } from '../api/client'

export type SessionUser = { id: string; username: string; display_name: string; role: 'admin' | 'member'; status: 'active' }

export const session = reactive<{ user: SessionUser | null; loaded: boolean }>({ user: null, loaded: false })

export async function loadSession() {
  try { session.user = await api<SessionUser>('/api/auth/me') } catch { session.user = null }
  session.loaded = true
}
```

- [ ] **Step 5: Implement login and registration views**

```vue
<!-- frontend/src/views/LoginView.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { SessionUser } from '../auth/session'

const emit = defineEmits<{ loggedIn: [user: SessionUser] }>()
const username = ref('')
const password = ref('')
const error = ref('')
const registrationOpen = ref(false)
onMounted(async () => {
  const config = await api<{ allow_registration: boolean }>('/api/auth/config')
  registrationOpen.value = config.allow_registration
})
async function submit() {
  error.value = ''
  try {
    const user = await api<SessionUser>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: username.value, password: password.value }) })
    emit('loggedIn', user)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '登录失败' }
}
</script>

<template>
  <main class="auth-card">
    <h1>MeetFlow</h1>
    <form @submit.prevent="submit">
      <label>用户名<input v-model="username" required /></label>
      <label>密码<input v-model="password" type="password" required /></label>
      <p v-if="error" class="error">{{ error }}</p>
      <button type="submit">登录</button>
    </form>
    <RouterLink v-if="registrationOpen" to="/register">申请账号</RouterLink>
  </main>
</template>
```

```vue
<!-- frontend/src/views/RegisterView.vue -->
<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api/client'
const username = ref('')
const displayName = ref('')
const password = ref('')
const submitted = ref(false)
const error = ref('')
async function submit() {
  try {
    await api('/api/auth/register', { method: 'POST', body: JSON.stringify({ username: username.value, display_name: displayName.value, password: password.value }) })
    submitted.value = true
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '注册失败' }
}
</script>
<template>
  <main class="auth-card">
    <h1>申请 MeetFlow 账号</h1>
    <p v-if="submitted">申请已提交，请等待管理员批准。</p>
    <form v-else @submit.prevent="submit">
      <label>用户名<input v-model="username" minlength="3" required /></label>
      <label>显示名称<input v-model="displayName" required /></label>
      <label>密码<input v-model="password" type="password" minlength="12" required /></label>
      <p v-if="error" class="error">{{ error }}</p>
      <button type="submit">提交申请</button>
    </form>
    <RouterLink to="/login">返回登录</RouterLink>
  </main>
</template>
```

```vue
<!-- frontend/src/views/WorkspaceView.vue -->
<template>
  <main><h1>共享会议工作区</h1><p>登录与管理员审批流程已就绪。</p></main>
</template>
```

```vue
<!-- frontend/src/views/AdminUsersView.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
type User = { id: string; username: string; display_name: string; role: string; status: string }
const users = ref<User[]>([])
const form = ref({ username: '', display_name: '', password: '' })
async function load() { users.value = await api<User[]>('/api/admin/users') }
async function transition(id: string, action: 'approve' | 'reject' | 'disable') {
  await api(`/api/admin/users/${id}/${action}`, { method: 'POST' })
  await load()
}
async function createFixedAccount() {
  await api('/api/admin/users', { method: 'POST', body: JSON.stringify(form.value) })
  form.value = { username: '', display_name: '', password: '' }
  await load()
}
async function resetPassword(user: User) {
  const password = window.prompt(`为 ${user.display_name} 设置至少 12 位的新密码`)
  if (!password || password.length < 12) return
  await api(`/api/admin/users/${user.id}/reset-password`, { method: 'POST', body: JSON.stringify({ password }) })
}
onMounted(load)
</script>
<template>
  <main>
    <h1>用户管理</h1>
    <form @submit.prevent="createFixedAccount">
      <input v-model="form.username" aria-label="固定账号用户名" required />
      <input v-model="form.display_name" aria-label="显示名称" required />
      <input v-model="form.password" aria-label="初始密码" type="password" minlength="12" required />
      <button>创建固定账号</button>
    </form>
    <article v-for="user in users" :key="user.id">
      <strong>{{ user.display_name }}</strong><span>{{ user.username }} · {{ user.status }}</span>
      <button v-if="user.status === 'pending'" @click="transition(user.id, 'approve')">批准</button>
      <button v-if="user.status === 'pending'" @click="transition(user.id, 'reject')">拒绝</button>
      <button v-if="user.status === 'active' && user.role !== 'admin'" @click="transition(user.id, 'disable')">禁用</button>
      <button v-if="user.role !== 'admin'" @click="resetPassword(user)">重置密码</button>
    </article>
  </main>
</template>
```

```vue
<!-- frontend/src/views/AccountView.vue -->
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { session } from '../auth/session'
const router = useRouter()
const currentPassword = ref('')
const newPassword = ref('')
const error = ref('')
async function changePassword() {
  try {
    await api('/api/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: currentPassword.value, new_password: newPassword.value }) })
    session.user = null
    await router.push('/login')
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '修改失败' }
}
</script>
<template>
  <main><h1>账号设置</h1><form @submit.prevent="changePassword">
    <label>当前密码<input v-model="currentPassword" type="password" required /></label>
    <label>新密码<input v-model="newPassword" type="password" minlength="12" required /></label>
    <p v-if="error" class="error">{{ error }}</p><button>修改密码</button>
  </form></main>
</template>
```

- [ ] **Step 6: Add router guards and an admin-only navigation shell**

```ts
// frontend/src/router.ts
import { createRouter, createWebHistory } from 'vue-router'
import { loadSession, session } from './auth/session'
import LoginView from './views/LoginView.vue'
import RegisterView from './views/RegisterView.vue'
import WorkspaceView from './views/WorkspaceView.vue'
import AccountView from './views/AccountView.vue'
import AdminUsersView from './views/AdminUsersView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/register', component: RegisterView, meta: { public: true } },
    { path: '/', component: WorkspaceView },
    { path: '/account', component: AccountView },
    { path: '/admin/users', component: AdminUsersView, meta: { admin: true } },
  ],
})

router.beforeEach(async (to) => {
  if (!session.loaded) await loadSession()
  if (!to.meta.public && !session.user) return '/login'
  if (to.meta.admin && session.user?.role !== 'admin') return '/'
})

export default router
```

```ts
// frontend/src/main.ts
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './styles.css'
createApp(App).use(router).mount('#app')
```

```vue
<!-- frontend/src/App.vue -->
<script setup lang="ts">
import { useRouter } from 'vue-router'
import { api } from './api/client'
import { session, type SessionUser } from './auth/session'
const router = useRouter()
function onLoggedIn(user: SessionUser) { session.user = user; router.push('/') }
async function logout() { await api('/api/auth/logout', { method: 'POST' }); session.user = null; router.push('/login') }
</script>
<template>
  <header v-if="session.user">
    <RouterLink to="/">会议</RouterLink>
    <RouterLink to="/account">账号</RouterLink>
    <RouterLink v-if="session.user.role === 'admin'" to="/admin/users">用户管理</RouterLink>
    <button @click="logout">退出</button>
  </header>
  <RouterView v-slot="{ Component }"><component :is="Component" @logged-in="onLoggedIn" /></RouterView>
</template>
```

```css
/* frontend/src/styles.css */
:root { font-family: Inter, system-ui, sans-serif; color: #172033; background: #f4f6fa; }
body { margin: 0; }
main, header { max-width: 1080px; margin: 0 auto; padding: 1rem; }
form, article { display: grid; gap: .75rem; padding: 1rem; background: white; border-radius: .75rem; }
label { display: grid; gap: .25rem; }
input, textarea, button { font: inherit; padding: .65rem; }
.auth-card { max-width: 420px; margin-top: 8vh; }
.error { color: #b42318; }
```

- [ ] **Step 7: Run frontend tests and production type-check/build**

Run: `cd frontend && npm test`

Expected: all tests pass.

Run: `cd frontend && npm run build`

Expected: TypeScript succeeds and `frontend/dist/index.html` is created.

- [ ] **Step 8: Commit the authenticated frontend shell**

```bash
git add frontend
git commit -m "feat: add authenticated Vue application shell"
```

## Stage 2: Meeting archive workflow

### Task 6: Meeting package model and CRUD API

**Files:**
- Create: `backend/app/meetings/__init__.py`
- Create: `backend/app/meetings/models.py`
- Create: `backend/app/meetings/schemas.py`
- Create: `backend/app/meetings/service.py`
- Create: `backend/app/meetings/router.py`
- Create: `backend/tests/meetings/test_meetings_api.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Test authenticated CRUD, search, and attribution**

```python
# backend/tests/meetings/test_meetings_api.py
def login_admin(client):
    client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-battery"})


def test_create_search_update_and_delete_meeting(client):
    login_admin(client)
    payload = {
        "title": "GRPO 数据集方案讨论",
        "project": "LLM Post-training",
        "meeting_type": "技术讨论",
        "meeting_date": "2026-07-17T13:30:00Z",
        "participants": ["张三", "李四", "我"],
        "raw_notes_markdown": "- AppWorld 数据完整",
        "conclusions_markdown": "1. 第一阶段使用 AppWorld",
    }
    created = client.post("/api/meetings", json=payload)
    assert created.status_code == 201
    meeting_id = created.json()["id"]
    assert created.json()["created_by"]["username"] == "admin"
    assert len(client.get("/api/meetings?q=GRPO").json()) == 1

    updated = client.put(f"/api/meetings/{meeting_id}", json={**payload, "title": "GRPO 方案复盘"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "GRPO 方案复盘"
    assert client.delete(f"/api/meetings/{meeting_id}").status_code == 204
```

Add reusable authenticated meeting fixtures after this test is green:

```python
# backend/tests/conftest.py additions
@pytest.fixture
def authenticated_client(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-battery"})
    assert response.status_code == 200
    return client


@pytest.fixture
def meeting_id(authenticated_client):
    response = authenticated_client.post("/api/meetings", json={
        "title": "Fixture meeting",
        "project": "MeetFlow",
        "meeting_type": "technical",
        "meeting_date": "2026-07-17T13:30:00Z",
        "participants": ["Admin"],
        "raw_notes_markdown": "Fixture notes",
        "conclusions_markdown": "Fixture conclusion",
    })
    assert response.status_code == 201
    return response.json()["id"]
```

- [ ] **Step 2: Run the test and verify the endpoint is absent**

Run: `.venv/bin/python -m pytest backend/tests/meetings/test_meetings_api.py -q`

Expected: test fails with 404.

- [ ] **Step 3: Create the four meeting-domain models**

```python
# backend/app/meetings/models.py
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(240), index=True)
    project: Mapped[str] = mapped_column(String(160), default="", index=True)
    meeting_type: Mapped[str] = mapped_column(String(120), default="")
    meeting_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    participants: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_notes_markdown: Mapped[str] = mapped_column(Text, default="")
    conclusions_markdown: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ActionItem(Base):
    __tablename__ = "action_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(String(500))
    owner: Mapped[str] = mapped_column(String(120), default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str] = mapped_column(String(160))
    size: Mapped[int] = mapped_column(Integer)
    attachment_type: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MeetingUpdate(Base):
    __tablename__ = "meeting_updates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    content_markdown: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

- [ ] **Step 4: Define create, update, summary, and complete-package schemas**

```python
# backend/app/meetings/schemas.py
from datetime import date, datetime
from pydantic import BaseModel, Field


class MeetingWrite(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    project: str = Field(default="", max_length=160)
    meeting_type: str = Field(default="", max_length=120)
    meeting_date: datetime
    participants: list[str] = Field(default_factory=list)
    raw_notes_markdown: str = ""
    conclusions_markdown: str = ""


class Actor(BaseModel):
    id: str
    username: str
    display_name: str


class MeetingSummary(BaseModel):
    id: str
    title: str
    project: str
    meeting_type: str
    meeting_date: datetime
    participants: list[str]
    conclusion_count: int
    open_action_count: int
    attachment_count: int
    created_by: Actor
    updated_by: Actor
    updated_at: datetime
```

- [ ] **Step 5: Implement service queries and router endpoints**

`MeetingService.list()` must use one aggregate query for child counts and `casefold`-compatible SQLite `lower(...) LIKE` matching over title and project. `MeetingService.get_package()` returns meeting data, actions, attachments, updates, and actor projections. Every write uses the dependency-provided current user for attribution.

```python
# backend/app/meetings/router.py
router = APIRouter(prefix="/api/meetings", tags=["meetings"], dependencies=[Depends(current_user)])

@router.get("")
def list_meetings(q: str = "", user: User = Depends(current_user), session: Session = Depends(get_session)):
    return MeetingService(session).list(q)

@router.post("", status_code=201)
def create_meeting(payload: MeetingWrite, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return MeetingService(session).create(payload, user)

@router.get("/{meeting_id}")
def get_meeting(meeting_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return MeetingService(session).get_package(meeting_id)

@router.put("/{meeting_id}")
def update_meeting(meeting_id: str, payload: MeetingWrite, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return MeetingService(session).update(meeting_id, payload, user)

@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    MeetingService(session).delete(meeting_id)
```

- [ ] **Step 6: Import meeting models before schema creation and include the router**

```python
# backend/app/main.py
from app.meetings.models import ActionItem, Attachment, Meeting, MeetingUpdate
from app.meetings.router import router as meetings_router
app.include_router(meetings_router)
```

- [ ] **Step 7: Run meeting and regression tests**

Run: `.venv/bin/python -m pytest backend/tests/meetings/test_meetings_api.py -q`

Expected: meeting CRUD test passes.

Run: `.venv/bin/python -m pytest -q`

Expected: all backend tests pass.

- [ ] **Step 8: Commit meeting CRUD**

```bash
git add backend/app/meetings backend/app/main.py backend/tests/meetings
git commit -m "feat: add shared meeting package CRUD"
```

### Task 7: Meeting timeline and detail editor UI

**Files:**
- Create: `frontend/src/components/MarkdownView.vue`
- Create: `frontend/src/components/MeetingCard.vue`
- Create: `frontend/src/views/MeetingsView.vue`
- Create: `frontend/src/views/MeetingDetailView.vue`
- Create: `frontend/src/tests/meetings.test.ts`
- Modify: `frontend/src/router.ts`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Test meeting cards and search behavior**

```ts
// frontend/src/tests/meetings.test.ts
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import MeetingsView from '../views/MeetingsView.vue'
import MarkdownView from '../components/MarkdownView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
apiMock.mockResolvedValue([{ id: 'm1', title: 'GRPO 数据集方案讨论', project: 'LLM Post-training', meeting_date: '2026-07-17T13:30:00Z', participants: ['我'], conclusion_count: 2, open_action_count: 1, attachment_count: 1, created_by: { display_name: 'Admin' }, updated_by: { display_name: 'Admin' } }])
vi.mock('../api/client', () => ({ api: apiMock }))

describe('MeetingsView', () => {
  it('renders and searches the meeting timeline', async () => {
    render(MeetingsView)
    expect(await screen.findByText('GRPO 数据集方案讨论')).toBeInTheDocument()
    await fireEvent.update(screen.getByLabelText('搜索会议'), 'GRPO')
    await fireEvent.submit(screen.getByRole('search'))
    expect(apiMock).toHaveBeenLastCalledWith('/api/meetings?q=GRPO')
  })

  it('sanitizes raw HTML in Markdown', () => {
    const { container } = render(MarkdownView, { props: { source: '<img src=x onerror="alert(1)">' } })
    expect(container.querySelector('img')).not.toHaveAttribute('onerror')
  })
})
```

- [ ] **Step 2: Run the test and verify the view is missing**

Run: `cd frontend && npm test -- meetings.test.ts`

Expected: test fails because `MeetingsView.vue` does not exist.

- [ ] **Step 3: Implement safe Markdown rendering**

```vue
<!-- frontend/src/components/MarkdownView.vue -->
<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'
const props = defineProps<{ source: string }>()
const html = computed(() => DOMPurify.sanitize(marked.parse(props.source, { async: false }) as string))
</script>
<template><div class="markdown" v-html="html" /></template>
```

- [ ] **Step 4: Implement timeline cards, debounced search, and create form**

`MeetingsView.vue` owns `q`, `meetings`, `loading`, and a modal-free inline create form. Submit exact `MeetingWrite` JSON, then navigate to `/meetings/{id}`. `MeetingCard.vue` displays meeting date, project, participants, child counts, creator, and updater.

```ts
async function load() {
  loading.value = true
  try { meetings.value = await api<MeetingSummary[]>(`/api/meetings?q=${encodeURIComponent(q.value)}`) }
  finally { loading.value = false }
}

async function createMeeting(payload: MeetingWrite) {
  const created = await api<{ id: string }>('/api/meetings', { method: 'POST', body: JSON.stringify(payload) })
  await router.push(`/meetings/${created.id}`)
}
```

- [ ] **Step 5: Implement the five-section meeting detail editor**

`MeetingDetailView.vue` loads one complete package, renders tabs for overview, notes, actions, attachments, and updates, and keeps an editable `MeetingWrite` draft. The notes tab contains separate textareas for `raw_notes_markdown` and `conclusions_markdown` with adjacent sanitized previews. On API failure, leave the draft untouched and show the error above the save button.

```ts
async function saveMeeting() {
  saving.value = true
  error.value = ''
  try {
    meeting.value = await api(`/api/meetings/${route.params.id}`, { method: 'PUT', body: JSON.stringify(draft.value) })
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '保存失败'
  } finally {
    saving.value = false
  }
}
```

- [ ] **Step 6: Add routes and test the production build**

```ts
// frontend/src/router.ts: replace WorkspaceView on `/` and add detail route
import MeetingsView from './views/MeetingsView.vue'

{ path: '/', component: MeetingsView },
{ path: '/meetings/:id', component: () => import('./views/MeetingDetailView.vue') }
```

Run: `cd frontend && npm test`

Expected: all frontend tests pass.

Run: `cd frontend && npm run build`

Expected: build succeeds without TypeScript errors.

- [ ] **Step 7: Commit meeting UI**

```bash
git add frontend/src
git commit -m "feat: add meeting timeline and package editor"
```

### Task 8: Structured action items and meeting updates

**Files:**
- Modify: `backend/app/meetings/schemas.py`
- Modify: `backend/app/meetings/service.py`
- Modify: `backend/app/meetings/router.py`
- Create: `backend/tests/meetings/test_actions_updates.py`
- Create: `frontend/src/components/ActionItemEditor.vue`
- Create: `frontend/src/views/OpenActionsView.vue`
- Modify: `frontend/src/views/MeetingDetailView.vue`
- Modify: `frontend/src/router.ts`

- [ ] **Step 1: Test action and update lifecycle**

```python
# backend/tests/meetings/test_actions_updates.py
def test_actions_and_updates_are_attributed_and_aggregated(authenticated_client, meeting_id):
    action = authenticated_client.post(f"/api/meetings/{meeting_id}/actions", json={"content": "调研数据集", "owner": "我", "due_date": "2026-07-20", "status": "open"})
    assert action.status_code == 201
    assert action.json()["created_by"]["username"] == "admin"
    assert len(authenticated_client.get("/api/actions?status=open").json()) == 1

    update = authenticated_client.post(f"/api/meetings/{meeting_id}/updates", json={"content_markdown": "完成第一轮数据加载测试。"})
    assert update.status_code == 201
    assert update.json()["created_by"]["username"] == "admin"
```

- [ ] **Step 2: Run the focused test and confirm 404 responses**

Run: `.venv/bin/python -m pytest backend/tests/meetings/test_actions_updates.py -q`

Expected: test fails because child-resource routes are missing.

- [ ] **Step 3: Add strict child-resource schemas and service methods**

```python
# backend/app/meetings/schemas.py additions
from typing import Literal


class ActionWrite(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    owner: str = Field(default="", max_length=120)
    due_date: date | None = None
    status: Literal["open", "done"] = "open"


class UpdateWrite(BaseModel):
    content_markdown: str = Field(min_length=1, max_length=20_000)
```

Service methods must verify the meeting exists, verify child ownership on update/delete, set `created_by` from the authenticated user, and return 404 for both absent and mismatched child IDs.

- [ ] **Step 4: Add action, global-open-action, and update routes**

Implement the exact routes from the design: meeting-scoped POST/PUT/DELETE for actions, `GET /api/actions?status=open`, and meeting-scoped POST/DELETE for updates. Register the global actions router separately so it does not conflict with `/api/meetings/{meeting_id}/actions`.

- [ ] **Step 5: Run backend tests**

Run: `.venv/bin/python -m pytest backend/tests/meetings -q`

Expected: all meeting tests pass.

- [ ] **Step 6: Build the action editor, global open-actions page, and append-only updates UI**

`ActionItemEditor.vue` emits `save` and `remove` with a fully typed `ActionWrite`. `OpenActionsView.vue` loads `/api/actions?status=open`, groups cards by meeting, and supports marking an item done. The updates tab appends a Markdown entry and lists author plus timestamp; it does not edit existing updates.

```ts
async function complete(item: ActionItem) {
  await api(`/api/meetings/${item.meeting_id}/actions/${item.id}`, {
    method: 'PUT',
    body: JSON.stringify({ content: item.content, owner: item.owner, due_date: item.due_date, status: 'done' }),
  })
  await load()
}
```

- [ ] **Step 7: Test and commit action tracking**

Run: `cd frontend && npm test && npm run build`

Expected: tests and build pass.

```bash
git add backend frontend/src
git commit -m "feat: add action tracking and meeting updates"
```

### Task 9: Safe attachment storage and API

**Files:**
- Create: `backend/app/attachments/__init__.py`
- Create: `backend/app/attachments/storage.py`
- Create: `backend/app/attachments/router.py`
- Create: `backend/tests/meetings/test_attachments.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/meetings/service.py`

- [ ] **Step 1: Test upload, download, size rejection, and cascade cleanup**

```python
# backend/tests/meetings/test_attachments.py
def test_upload_download_and_delete_image(authenticated_client, meeting_id):
    uploaded = authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={"file": ("board.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
    )
    assert uploaded.status_code == 201
    attachment = uploaded.json()
    assert attachment["attachment_type"] == "image"
    download = authenticated_client.get(f"/api/meetings/{meeting_id}/attachments/{attachment['id']}")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("image/png")
    assert authenticated_client.delete(f"/api/meetings/{meeting_id}/attachments/{attachment['id']}").status_code == 204


def test_oversized_upload_leaves_no_database_or_file(authenticated_client, meeting_id, settings):
    authenticated_client.app.state.attachment_storage.max_bytes = 8
    response = authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={"file": ("too-big.txt", b"123456789", "text/plain")},
    )
    assert response.status_code == 413
    assert not any(path.is_file() for path in (settings.data_dir / "uploads").rglob("*"))
    assert authenticated_client.get(f"/api/meetings/{meeting_id}").json()["attachments"] == []


def test_deleting_meeting_removes_attachment_directory(authenticated_client, meeting_id, settings):
    authenticated_client.post(
        f"/api/meetings/{meeting_id}/attachments",
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )
    assert authenticated_client.delete(f"/api/meetings/{meeting_id}").status_code == 204
    assert not (settings.data_dir / "uploads" / meeting_id).exists()
```

- [ ] **Step 2: Run tests and confirm missing routes**

Run: `.venv/bin/python -m pytest backend/tests/meetings/test_attachments.py -q`

Expected: tests fail with 404.

- [ ] **Step 3: Implement safe atomic storage**

```python
# backend/app/attachments/storage.py
import os
import tempfile
import uuid
from pathlib import Path

from app.errors import AppError

INLINE_IMAGES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def sniff_inline_image(path: Path) -> str | None:
    header = path.read_bytes()[:16]
    if header.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if header.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")): return "image/gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP": return "image/webp"
    return None


class AttachmentStorage:
    def __init__(self, data_dir: Path, max_bytes: int):
        self.root = (data_dir / "uploads").resolve()
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def meeting_dir(self, meeting_id: str) -> Path:
        target = (self.root / meeting_id).resolve()
        if self.root not in target.parents:
            raise AppError(400, "invalid_path", "附件路径无效")
        return target

    async def save(self, meeting_id: str, upload) -> tuple[str, Path, int]:
        target_dir = self.meeting_dir(meeting_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload.filename or "file").suffix[:16]
        stored_name = f"{uuid.uuid4()}{suffix}"
        final_path = target_dir / stored_name
        size = 0
        fd, temp_name = tempfile.mkstemp(dir=target_dir, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as stream:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise AppError(413, "attachment_too_large", "单个附件不能超过 20 MB")
                    stream.write(chunk)
            os.replace(temp_name, final_path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        return stored_name, final_path, size
```

- [ ] **Step 4: Implement upload transaction cleanup and safe download headers**

The upload route calls `AttachmentStorage.save()`, then calls `sniff_inline_image(final_path)`. A recognized image uses the detected MIME and `attachment_type="image"`; every other file uses a normalized client MIME or `application/octet-stream` and `attachment_type="file"`. Insert `Attachment` and delete the stored file if `session.commit()` fails. Download uses `FileResponse`; only `INLINE_IMAGES` use `inline`, while every other MIME type uses `attachment`. Delete verifies both meeting and attachment IDs before deleting the database row, then unlinks the file with `missing_ok=True`.

```python
disposition = "inline" if attachment.mime_type in INLINE_IMAGES else "attachment"
return FileResponse(
    path,
    media_type=attachment.mime_type,
    filename=attachment.original_name,
    content_disposition_type=disposition,
)
```

Initialize storage once, expose it on app state, and include the attachment router:

```python
# backend/app/main.py inside create_app
from app.attachments.router import router as attachments_router
from app.attachments.storage import AttachmentStorage

attachment_storage = AttachmentStorage(resolved.data_dir, resolved.max_upload_bytes)
app.state.attachment_storage = attachment_storage
app.include_router(attachments_router)
```

- [ ] **Step 5: Connect meeting deletion to attachment-directory cleanup**

After the meeting delete transaction commits, call `shutil.rmtree(storage.meeting_dir(meeting_id), ignore_errors=True)`. Do not restore deleted database rows when disk cleanup fails; log the path-free meeting ID and exception class.

- [ ] **Step 6: Run attachment and regression tests**

Run: `.venv/bin/python -m pytest backend/tests/meetings/test_attachments.py -q`

Expected: all attachment tests pass.

Run: `.venv/bin/python -m pytest -q`

Expected: all backend tests pass.

- [ ] **Step 7: Commit attachment persistence**

```bash
git add backend/app/attachments backend/app/meetings backend/app/main.py backend/tests/meetings
git commit -m "feat: add safe meeting attachments"
```

### Task 10: Attachment gallery and final meeting workflow UI

**Files:**
- Create: `frontend/src/components/AttachmentPanel.vue`
- Modify: `frontend/src/views/MeetingDetailView.vue`
- Modify: `frontend/src/components/MeetingCard.vue`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/tests/meetings.test.ts`

- [ ] **Step 1: Add a failing attachment panel test**

```ts
import AttachmentPanel from '../components/AttachmentPanel.vue'

it('uploads a file and refreshes attachments', async () => {
  render(AttachmentPanel, { props: { meetingId: 'm1', attachments: [] } })
  const file = new File(['notes'], 'notes.txt', { type: 'text/plain' })
  await fireEvent.update(screen.getByLabelText('上传附件'), file)
  await fireEvent.click(screen.getByRole('button', { name: '上传' }))
  expect(apiMock).toHaveBeenCalledWith('/api/meetings/m1/attachments', expect.objectContaining({ method: 'POST' }))
})
```

- [ ] **Step 2: Implement image cards and generic file cards**

`AttachmentPanel.vue` uses the authenticated download URL directly for JPEG, PNG, GIF, and WebP thumbnails. Generic cards show original name, formatted byte size, uploader, download link, and delete button. The upload button is disabled while a request is active and rejects files over 20 MB before sending.

```ts
const maxBytes = 20 * 1024 * 1024
async function upload() {
  if (!selected.value) return
  if (selected.value.size > maxBytes) { error.value = '单个附件不能超过 20 MB'; return }
  const body = new FormData()
  body.append('file', selected.value)
  await api(`/api/meetings/${props.meetingId}/attachments`, { method: 'POST', body })
  emit('changed')
}
```

- [ ] **Step 3: Finish the overview counts and destructive confirmation**

The overview tab shows conclusions, open actions, and the first four attachment cards. The delete-meeting button must call `window.confirm('删除后将同时移除行动项和附件，确定继续？')`; cancel performs no request.

- [ ] **Step 4: Run all frontend verification**

Run: `cd frontend && npm test`

Expected: all UI tests pass.

Run: `cd frontend && npm run build`

Expected: production build passes.

- [ ] **Step 5: Commit the complete meeting workflow**

```bash
git add frontend/src
git commit -m "feat: complete meeting archive workflow"
```

## Stage 3: Plugin contract and deployment

### Task 11: Plugin manifest discovery and restart-loaded registry

**Files:**
- Create: `backend/app/plugins/__init__.py`
- Create: `backend/app/plugins/contracts.py`
- Create: `backend/app/plugins/models.py`
- Create: `backend/app/plugins/manager.py`
- Create: `backend/tests/plugins/test_discovery.py`
- Create: `plugins/plugins.yaml`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Test empty, valid, invalid, and failing plugins**

```python
# backend/tests/plugins/test_discovery.py
from fastapi.testclient import TestClient
from app.main import create_app


def test_empty_registry_does_not_block_startup(client):
    assert client.get("/api/health").status_code == 200
    assert client.app.state.plugin_manager.loaded_actions() == []


def test_broken_plugin_is_reported_without_blocking_core(plugin_factory, settings):
    plugin_factory(
        "broken",
        manifest={"id": "broken", "name": "Broken", "version": "0.1.0", "api_version": 1, "backend_entry": "backend.py"},
        backend="raise RuntimeError('broken import')",
        enabled=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.app.state.plugin_manager.errors()[0].plugin_id == "broken"
```

```python
# backend/tests/conftest.py additions
import yaml


@pytest.fixture
def plugin_factory(settings):
    registry = {"plugins": {}}
    settings.plugins_dir.mkdir(parents=True, exist_ok=True)

    def create(plugin_id: str, manifest: dict, backend: str, enabled: bool):
        plugin_dir = settings.plugins_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
        (plugin_dir / manifest["backend_entry"]).write_text(backend, encoding="utf-8")
        registry["plugins"][plugin_id] = {"path": plugin_id, "enabled": enabled}
        (settings.plugins_dir / "plugins.yaml").write_text(yaml.safe_dump(registry), encoding="utf-8")
        return plugin_dir

    return create
```

- [ ] **Step 2: Run tests and confirm plugin manager is absent**

Run: `.venv/bin/python -m pytest backend/tests/plugins/test_discovery.py -q`

Expected: tests fail because `plugin_manager` is not installed on app state.

- [ ] **Step 3: Define strict manifest and meeting-action contracts**

```python
# backend/app/plugins/contracts.py
from collections.abc import Awaitable, Callable
from typing import Any
from pydantic import BaseModel, Field


class ConfigField(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: str
    required: bool = False


class PluginManifest(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    version: str
    api_version: int
    backend_entry: str = "backend.py"
    description: str = ""
    config_schema: dict[str, list[ConfigField]] = Field(default_factory=dict)


class PluginLoadError(BaseModel):
    plugin_id: str
    error_type: str
    message: str


class MeetingAction:
    def __init__(self, action_id: str, label: str, description: str, admin_only: bool, input_schema: dict[str, Any], output_schema: dict[str, Any], handler: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]):
        self.action_id = action_id
        self.label = label
        self.description = description
        self.admin_only = admin_only
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.handler = handler


class PluginRegistry:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.actions: dict[str, MeetingAction] = {}

    def register_meeting_action(self, action: MeetingAction) -> None:
        if not action.action_id.startswith(f"{self.plugin_id}."):
            raise ValueError("action_id must be prefixed by plugin id")
        if action.action_id in self.actions:
            raise ValueError("duplicate action_id")
        self.actions[action.action_id] = action
```

- [ ] **Step 4: Add persistent plugin enabled-state model**

```python
# backend/app/plugins/models.py
class PluginState(Base):
    __tablename__ = "plugin_states"
    plugin_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
```

- [ ] **Step 5: Implement two-phase discovery and startup-only code loading**

`PluginManager.discover()` reads `plugins.yaml`, resolves every path under the configured plugin root, validates `plugin.yaml`, and returns descriptors without importing Python. Database state overrides YAML `enabled`. `PluginManager.load_enabled()` imports entry files with `importlib.util`, creates a per-plugin registry, calls `register(registry)`, rejects action IDs not prefixed with the plugin ID, and catches each plugin exception separately.

```python
def resolve_entry(plugin_root: Path, plugin_dir: Path, entry: str) -> Path:
    root = plugin_root.resolve()
    directory = plugin_dir.resolve()
    target = (directory / entry).resolve()
    if root not in directory.parents or directory not in target.parents:
        raise ValueError("plugin path escapes plugin directory")
    return target
```

- [ ] **Step 6: Initialize the manager during app startup**

```python
# backend/app/main.py; replace the existing startup handler
plugin_manager = PluginManager(resolved.plugins_dir, database)
app.state.plugin_manager = plugin_manager

@app.on_event("startup")
def startup():
    resolved.data_dir.mkdir(parents=True, exist_ok=True)
    resolved.plugins_dir.mkdir(parents=True, exist_ok=True)
    database.create_schema()
    with database.session() as session:
        auth_service.bootstrap_admin(session)
    plugin_manager.load_enabled()
```

- [ ] **Step 7: Create an empty production registry**

```yaml
# plugins/plugins.yaml
plugins: {}
```

- [ ] **Step 8: Run plugin and regression tests**

Run: `.venv/bin/python -m pytest backend/tests/plugins/test_discovery.py -q`

Expected: discovery tests pass.

Run: `.venv/bin/python -m pytest -q`

Expected: all backend tests pass.

- [ ] **Step 9: Commit plugin discovery**

```bash
git add backend/app/plugins backend/app/main.py backend/tests/plugins plugins
git commit -m "feat: add restart-loaded plugin registry"
```

### Task 12: Encrypted plugin configuration and generic meeting actions

**Files:**
- Create: `backend/app/plugins/secrets.py`
- Create: `backend/app/plugins/router.py`
- Create: `backend/tests/plugins/test_config.py`
- Create: `backend/tests/plugins/test_actions.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/app/plugins/models.py`
- Modify: `backend/app/plugins/manager.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Test encryption, response redaction, discovery, and action failure isolation**

```python
# backend/tests/conftest.py additions
@pytest.fixture
def plugin_client(settings, plugin_factory):
    plugin_factory(
        "test-ai",
        manifest={
            "id": "test-ai",
            "name": "Test AI",
            "version": "0.1.0",
            "api_version": 1,
            "backend_entry": "backend.py",
            "config_schema": {
                "fields": [{"key": "model", "type": "string", "required": True}],
                "secrets": [{"key": "api_key", "type": "secret", "required": True}],
            },
        },
        backend='''
from app.plugins.contracts import MeetingAction

async def summarize(context, payload, config):
    return {"markdown": "# Draft summary", "suggested_patch": {"conclusions_markdown": "Draft conclusion"}}

def register(registry):
    registry.register_meeting_action(MeetingAction(
        action_id="test-ai.summarize",
        label="生成会议纪要",
        description="生成测试纪要草稿",
        admin_only=False,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        handler=summarize,
    ))
''',
        enabled=True,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        login = test_client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-battery"})
        assert login.status_code == 200
        yield test_client


@pytest.fixture
def plugin_meeting_id(plugin_client):
    response = plugin_client.post("/api/meetings", json={
        "title": "Plugin meeting",
        "project": "MeetFlow",
        "meeting_type": "technical",
        "meeting_date": "2026-07-17T13:30:00Z",
        "participants": ["Admin"],
        "raw_notes_markdown": "Summarize this",
        "conclusions_markdown": "",
    })
    assert response.status_code == 201
    return response.json()["id"]


# backend/tests/plugins/test_config.py
from app.plugins.models import PluginConfig


def test_admin_sets_secret_but_never_reads_plaintext(plugin_client):
    response = plugin_client.put("/api/admin/plugins/test-ai/config", json={"api_key": "secret-value", "model": "test-model"})
    assert response.status_code == 200
    assert response.json()["api_key"] == {"configured": True}
    assert "secret-value" not in str(response.json())
    with plugin_client.app.state.database.session() as session:
        row = session.get(PluginConfig, {"plugin_id": "test-ai", "config_key": "api_key"})
        assert row.stored_value != "secret-value"


# backend/tests/plugins/test_actions.py
def test_user_discovers_and_executes_registered_action(plugin_client, plugin_meeting_id):
    plugin_client.put("/api/admin/plugins/test-ai/config", json={"api_key": "secret-value", "model": "test-model"})
    actions = plugin_client.get("/api/plugins/actions").json()
    assert actions[0]["action_id"] == "test-ai.summarize"
    result = plugin_client.post(f"/api/meetings/{plugin_meeting_id}/plugin-actions/test-ai.summarize", json={})
    assert result.status_code == 200
    assert result.json()["markdown"] == "# Draft summary"
```

- [ ] **Step 2: Derive a stable Fernet key and define plugin config rows**

```python
# backend/app/plugins/secrets.py
import base64
import hashlib
from cryptography.fernet import Fernet


class SecretBox:
    def __init__(self, app_secret_key: str):
        digest = hashlib.sha256(f"meetflow-plugin-config:{app_secret_key}".encode()).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode()).decode()
```

```python
# backend/app/plugins/models.py
class PluginConfig(Base):
    __tablename__ = "plugin_configs"
    plugin_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    config_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    stored_value: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
```

- [ ] **Step 3: Add admin-only list, enable, and config endpoints**

`GET /api/admin/plugins` calls manifest-only `discover()` so newly mounted plugins appear without importing them. `PUT /config` rejects undeclared keys, encrypts declared secrets, and returns `{"configured": true}` for secrets. Omitted keys remain unchanged, JSON `null` explicitly clears a key, and an empty secret string is rejected. `PUT /enabled` persists the next-start state and returns `{"restart_required": true}`.

- [ ] **Step 4: Add action discovery and generic execution endpoints**

```python
@router.get("/api/plugins/actions")
def list_actions(request: Request, user: User = Depends(current_user)):
    return request.app.state.plugin_manager.visible_actions(user.role)


@router.post("/api/meetings/{meeting_id}/plugin-actions/{action_id}")
async def run_action(request: Request, meeting_id: str, action_id: str, payload: dict, user: User = Depends(current_user), session: Session = Depends(get_session)):
    context = MeetingService(session).plugin_context(meeting_id, user)
    return await asyncio.wait_for(
        request.app.state.plugin_manager.invoke(action_id, context=context, payload=payload, session=session),
        timeout=60,
    )
```

Before invocation, validate `payload` against the action input schema with `jsonschema.validate`. Invoke the handler as `await handler(context, payload, decrypted_config)`, validate its result against the output schema, and then return it. Map timeout to `504 plugin_timeout`, schema violations to `502 plugin_invalid_output`, and every other plugin exception to `502 plugin_failed`; log plugin ID, action ID, and exception class without config values. The plugin context contains attachment metadata but no file paths or bytes.

- [ ] **Step 5: Run plugin tests and verify no secret leakage**

Run: `.venv/bin/python -m pytest backend/tests/plugins -q`

Expected: all plugin tests pass and captured responses/logs do not contain `secret-value`.

Run: `.venv/bin/python -m pytest -q`

Expected: all backend tests pass.

- [ ] **Step 6: Commit the plugin execution contract**

```bash
git add backend/app/plugins backend/app/meetings backend/app/main.py backend/tests/plugins
git commit -m "feat: add configurable meeting plugin actions"
```

### Task 13: Administrator plugin UI and generic action result panel

**Files:**
- Create: `frontend/src/views/AdminPluginsView.vue`
- Create: `frontend/src/components/PluginActionPanel.vue`
- Create: `frontend/src/tests/plugin-actions.test.ts`
- Modify: `frontend/src/views/MeetingDetailView.vue`
- Modify: `frontend/src/router.ts`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Test action discovery and editable draft output**

```ts
// frontend/src/tests/plugin-actions.test.ts
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'
import PluginActionPanel from '../components/PluginActionPanel.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api/client', () => ({ api: apiMock }))

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockImplementation((path: string) => {
    if (path === '/api/plugins/actions') return Promise.resolve([{ action_id: 'test-ai.summarize', label: '生成会议纪要', description: '生成草稿', input_schema: { type: 'object' } }])
    return Promise.resolve({ markdown: '# Draft summary', suggested_patch: { conclusions_markdown: 'Draft conclusion' } })
  })
})

it('runs an action and exposes an editable draft without auto-saving', async () => {
  render(PluginActionPanel, { props: { meetingId: 'm1' } })
  await screen.findByRole('button', { name: '生成会议纪要' })
  await fireEvent.click(screen.getByRole('button', { name: '生成会议纪要' }))
  expect(await screen.findByDisplayValue('# Draft summary')).toBeInTheDocument()
  expect(apiMock).not.toHaveBeenCalledWith('/api/meetings/m1', expect.objectContaining({ method: 'PUT' }))
})
```

- [ ] **Step 2: Implement manifest-driven admin configuration forms**

`AdminPluginsView.vue` renders fields from `config_schema.fields` and password inputs from `config_schema.secrets`. A configured secret input starts blank with “已配置”; blank submission leaves it unchanged, explicit clear requires a separate confirmation button. The enabled toggle displays “重启后生效”. Load errors are displayed per plugin and do not block other cards.

- [ ] **Step 3: Implement generic meeting actions**

`PluginActionPanel.vue` loads `/api/plugins/actions`, runs the selected action, and renders returned Markdown plus `suggested_patch` in editable controls. The “应用到会议” button emits the edited patch to `MeetingDetailView`; only that parent calls the ordinary meeting PUT endpoint.

```ts
const emit = defineEmits<{ apply: [patch: { conclusions_markdown?: string; raw_notes_markdown?: string }] }>()
function applyDraft() {
  emit('apply', editablePatch.value)
}
```

- [ ] **Step 4: Protect admin plugin route and navigation**

```ts
{ path: '/admin/plugins', component: () => import('./views/AdminPluginsView.vue'), meta: { admin: true } }
```

Only render the user/plugin admin links when `session.user?.role === 'admin'`.

- [ ] **Step 5: Run UI tests and build**

Run: `cd frontend && npm test`

Expected: all tests pass.

Run: `cd frontend && npm run build`

Expected: build succeeds.

- [ ] **Step 6: Commit plugin administration UI**

```bash
git add frontend/src
git commit -m "feat: add plugin administration and action UI"
```

### Task 14: Single-container Docker deployment and persistence acceptance

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `scripts/start.sh`
- Create: `README.md`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_static_app.py`

- [ ] **Step 1: Test static SPA fallback without intercepting `/api`**

```python
# backend/tests/test_static_app.py
def test_unknown_api_route_is_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
```

- [ ] **Step 2: Serve built assets and SPA routes only outside `/api`**

In production, mount `/app/frontend-dist/assets` at `/assets` and add a final non-API route that returns `index.html` when present. Never return the SPA for `/api/*`.

```python
@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise AppError(404, "not_found", "接口不存在")
    index = Path("/app/frontend-dist/index.html")
    if not index.exists():
        raise AppError(404, "not_found", "页面不存在")
    return FileResponse(index)
```

- [ ] **Step 3: Create the multi-stage production image**

```dockerfile
# Dockerfile
FROM node:22-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir .
COPY --from=frontend-build /src/frontend/dist ./frontend-dist
RUN mkdir -p /app/data /app/plugins
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

- [ ] **Step 4: Create Compose mounts and health check**

```yaml
# docker-compose.yml
services:
  meetflow:
    build: .
    env_file: .env
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./plugins:/app/plugins:ro
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
```

- [ ] **Step 5: Add safe environment and ignore templates**

```env
# .env.example
APP_ENV=development
DATABASE_URL=sqlite:///./data/meetflow.db
DATA_DIR=data
PLUGINS_DIR=plugins
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-admin-password
APP_SECRET_KEY=change-this-random-secret-before-use-0001
ALLOW_REGISTRATION=true
SECURE_COOKIES=false
TRUSTED_ORIGINS=http://localhost:8000
```

Run: `chmod +x scripts/start.sh` and keep the executable bit in Git.

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
frontend/node_modules/
frontend/dist/
data/
plugins/*/
```

- [ ] **Step 6: Add the only supported start wrapper**

```bash
#!/usr/bin/env bash
set -euo pipefail
mode="${1:-local}"
if [[ "$mode" == "docker" ]]; then
  docker compose up --build
else
  .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload &
  backend_pid=$!
  trap 'kill "$backend_pid"' EXIT
  npm --prefix frontend run dev
fi
```

- [ ] **Step 7: Document local, Docker, remote HTTPS, backup, and plugin operations**

`README.md` must include exact commands for copying `.env.example`, generating `APP_SECRET_KEY`, starting through `./scripts/start.sh local` or `./scripts/start.sh docker`, mounting a plugin, restarting after enable changes, backing up `data/`, and placing Caddy/Nginx with HTTPS in front. State that remote deployment must set `APP_ENV=production`, `SECURE_COOKIES=true`, and `TRUSTED_ORIGINS=https://the-real-domain`; also state that rotating `APP_SECRET_KEY` invalidates sessions and encrypted plugin secrets.

- [ ] **Step 8: Run complete local verification**

Run: `.venv/bin/python -m pytest -q`

Expected: all backend tests pass.

Run: `cd frontend && npm test && npm run build`

Expected: all frontend tests and the production build pass.

- [ ] **Step 9: Build and run the container**

Run: `cp .env.example .env`, replace `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `APP_SECRET_KEY`, then run `./scripts/start.sh docker`.

Expected: Compose reports `meetflow` healthy and `curl http://127.0.0.1:8000/api/health` returns `{"status":"ok"}`.

- [ ] **Step 10: Verify persistence and the 2 GB boundary**

Create an approved member, meeting, action, and attachment through the UI. Run `docker compose down`, then `docker compose up -d`; verify all four remain. Run `docker stats --no-stream` and verify the MeetFlow container uses less than 2 GB.

- [ ] **Step 11: Commit deployment assets**

```bash
git add .env.example .gitignore Dockerfile docker-compose.yml scripts README.md backend/app/main.py backend/tests/test_static_app.py
git commit -m "feat: add single-container MeetFlow deployment"
```

## Final acceptance checkpoint

- [ ] Run: `.venv/bin/python -m pytest -q` — expected: all backend tests pass.
- [ ] Run: `cd frontend && npm test` — expected: all frontend tests pass.
- [ ] Run: `cd frontend && npm run build` — expected: production frontend build succeeds.
- [ ] Run: `docker compose build` — expected: the single MeetFlow image builds.
- [ ] Run: `docker compose up -d` and poll `/api/health` — expected: healthy.
- [ ] Complete the approved demo flow with a fixed account, meeting, Markdown notes, conclusions, two action items, PNG, PDF, search, and open-actions page.
- [ ] Mount the test plugin, enable/configure it as admin, restart, and verify its generic meeting action appears and returns an editable draft.
- [ ] Run: `git status --short` — expected: no uncommitted generated files or secrets.
