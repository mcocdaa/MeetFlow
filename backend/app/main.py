from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401 - registers SQLAlchemy metadata
from app.agendas.router import router as agendas_router
from app.attachments.router import router as attachments_router
from app.attachments.storage import AttachmentStorage
from app.auth.router import admin_router, router as auth_router
from app.auth.service import AuthService
from app.config import Settings
from app.collaboration.router import router as collaboration_router
from app.database import Database
from app.errors import install_error_handlers
from app.meetings.router import router as meetings_router
from app.outcomes.router import router as outcomes_router
from app.plugins.manager import PluginManager
from app.plugins.router import (
    actions_router as plugin_actions_router,
    admin_router as plugin_admin_router,
    meeting_actions_router,
)
from app.projects.router import router as projects_router, updates_router
from app.schema_guard import reject_legacy_schema
from app.workspace.router import router as workspace_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    database = Database(resolved.database_url)
    auth_service = AuthService(resolved)
    attachment_storage = AttachmentStorage(resolved.data_dir, resolved.max_upload_bytes)
    plugin_manager = PluginManager(
        resolved.plugins_dir, database, resolved.app_secret_key
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        resolved.data_dir.mkdir(parents=True, exist_ok=True)
        resolved.plugins_dir.mkdir(parents=True, exist_ok=True)
        attachment_storage.initialize()
        if resolved.app_env == "test":
            database.create_schema()
        else:
            reject_legacy_schema(database.engine)
            database.migrate()
        with database.session() as session:
            auth_service.bootstrap_admin(session)
        plugin_manager.load_enabled()
        yield
        database.engine.dispose()

    app = FastAPI(title="MeetFlow", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.database = database
    app.state.auth_service = auth_service
    app.state.attachment_storage = attachment_storage
    app.state.plugin_manager = plugin_manager
    install_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(meetings_router)
    app.include_router(agendas_router)
    app.include_router(attachments_router)
    app.include_router(plugin_admin_router)
    app.include_router(plugin_actions_router)
    app.include_router(meeting_actions_router)
    app.include_router(projects_router)
    app.include_router(updates_router)
    app.include_router(outcomes_router)
    app.include_router(workspace_router)
    app.include_router(collaboration_router)

    @app.middleware("http")
    async def reject_cross_origin_writes(request: Request, call_next):
        origin = request.headers.get("origin", "").rstrip("/")
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin
            and origin not in resolved.trusted_origin_set
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "origin_forbidden",
                        "message": "请求来源不受信任",
                    }
                },
            )
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    frontend_dist = resolved.frontend_dist.resolve()
    frontend_index = frontend_dist / "index.html"
    frontend_assets = frontend_dist / "assets"
    if frontend_index.is_file():
        if frontend_assets.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=frontend_assets),
                name="frontend-assets",
            )

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_frontend(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            return FileResponse(frontend_index)

    return app


app = create_app()
