from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.meetings.models import utcnow
from app.plugins.models import PluginEvent, PluginEventStatus


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "stored_value",
}


def _validate_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("event payload must be a mapping")

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized = str(key).strip().lower().replace("-", "_")
                if normalized in _SENSITIVE_KEYS or normalized.endswith("_secret"):
                    raise ValueError("event payload contains sensitive data")
                walk(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                walk(child)

    walk(value)
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("event payload must be JSON serializable") from exc
    return dict(value)


def record_plugin_event(
    session: Session,
    *,
    event_type: str,
    target_type: str,
    target_id: str,
    payload: Mapping[str, Any],
    event_id: str | None = None,
    payload_version: int = 1,
) -> PluginEvent:
    """Insert an outbox event once; the caller owns the surrounding commit."""
    if not event_type or not target_type or not target_id:
        raise ValueError("event type and target are required")
    if payload_version < 1:
        raise ValueError("payload version must be positive")
    safe_payload = _validate_payload(payload)
    stable_id = event_id or f"{event_type}:{target_type}:{target_id}:{uuid.uuid4()}"
    existing = session.get(PluginEvent, stable_id)
    if existing is not None:
        return existing
    event = PluginEvent(
        event_id=stable_id,
        event_type=event_type,
        payload_version=payload_version,
        target_type=target_type,
        target_id=target_id,
        payload_json=safe_payload,
        status=PluginEventStatus.queued,
        attempts=0,
        next_attempt_at=utcnow(),
    )
    session.add(event)
    session.flush()
    return event
