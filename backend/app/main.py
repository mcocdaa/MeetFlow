from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.database import Database
from app.errors import install_error_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    database = Database(resolved.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        resolved.data_dir.mkdir(parents=True, exist_ok=True)
        resolved.plugins_dir.mkdir(parents=True, exist_ok=True)
        database.create_schema()
        yield
        database.engine.dispose()

    app = FastAPI(title="MeetFlow", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.database = database
    install_error_handlers(app)

    @app.middleware("http")
    async def reject_cross_origin_writes(
        request: Request, call_next
    ):
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

    return app


app = create_app()
