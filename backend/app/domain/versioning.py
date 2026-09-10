from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError


def require_version(expected_version: int, actual_version: int) -> None:
    if expected_version != actual_version:
        raise AppError(
            409,
            "version_conflict",
            "项目已被其他操作更新，请刷新后重试",
            details={
                "expected_version": expected_version,
                "actual_version": actual_version,
            },
        )


@dataclass(frozen=True)
class StaleCheck:
    """One optimistic-lock expectation to verify after a failed commit."""

    model: type
    entity_id: str
    expected_version: int
    # When the row is gone: a code here raises 404; None skips the check.
    not_found_code: str | None = None
    not_found_message: str = ""


def resolve_stale(
    session: Session,
    exc: Exception,
    *checks: StaleCheck,
    conflict_message: str,
    include_fallback_versions: bool = False,
) -> None:
    """Diagnose a failed optimistic-lock commit and re-raise the right error.

    Rolls back, then verifies every expected version against the database:
    a missing row raises its not-found error, a mismatched version raises
    409 with version details, and otherwise the caller's generic conflict
    message is raised. With ``include_fallback_versions`` the generic 409
    also carries the last check's expected/actual versions.
    """
    session.rollback()
    last_actual: int | None = None
    for check in checks:
        actual = session.scalar(
            select(check.model.version).where(check.model.id == check.entity_id)
        )
        if actual is None:
            if check.not_found_code is None:
                continue
            raise AppError(
                404, check.not_found_code, check.not_found_message
            ) from exc
        last_actual = actual
        require_version(check.expected_version, actual)
    details = None
    if include_fallback_versions and checks and last_actual is not None:
        details = {
            "expected_version": checks[-1].expected_version,
            "actual_version": last_actual,
        }
    raise AppError(
        409, "version_conflict", conflict_message, details=details
    ) from exc
