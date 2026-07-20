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
