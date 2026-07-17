from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = []
        for error in exc.errors():
            location = [
                str(part) for part in error.get("loc", ()) if part != "body"
            ]
            fields.append(
                {
                    "field": ".".join(location),
                    "message": error.get("msg", "Invalid value"),
                    "type": error.get("type", "validation_error"),
                }
            )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "请求参数无效",
                    "fields": fields,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if exc.status_code == 404:
            code, message = "not_found", "接口不存在"
        elif exc.status_code == 405:
            code, message = "method_not_allowed", "请求方法不受支持"
        else:
            code, message = "http_error", "请求无法处理"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": message}},
            headers=exc.headers,
        )
