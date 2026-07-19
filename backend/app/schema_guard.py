from sqlalchemy import Engine, inspect


class LegacyDatabaseError(RuntimeError):
    pass


def reject_legacy_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "meetings" not in tables or "alembic_version" in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("meetings")}
    if "project" in columns and "project_id" not in columns:
        raise LegacyDatabaseError(
            "MeetFlow v0.1 database detected; archive data/ and start fresh"
        )
