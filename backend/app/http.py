from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def _z_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def utc_content(value: Any) -> Any:
    """Recursively render datetimes as UTC with a Z suffix.

    SQLite round-trips datetimes as naive; treat them as UTC. Aware
    datetimes in other timezones are converted to UTC first.
    """
    return jsonable_encoder(value, custom_encoder={datetime: _z_iso})


def utc_response(value: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=utc_content(value),
    )
