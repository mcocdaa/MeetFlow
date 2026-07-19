from collections.abc import Generator
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def _has_migration_resources(config_path: Path) -> bool:
    migrations = config_path.parent / "migrations"
    return all(
        path.is_file()
        for path in (
            config_path,
            migrations / "env.py",
            migrations / "script.py.mako",
            migrations / "versions" / "0001_meetflow_1.py",
        )
    )


def migration_config_path() -> Path:
    source_config = Path(__file__).resolve().parents[1] / "alembic.ini"
    if _has_migration_resources(source_config):
        return source_config

    try:
        meetflow_distribution = distribution("meetflow")
    except PackageNotFoundError:
        meetflow_distribution = None

    if meetflow_distribution is not None:
        for package_path in meetflow_distribution.files or ():
            if package_path.as_posix().endswith("share/meetflow/alembic.ini"):
                installed_config = Path(
                    meetflow_distribution.locate_file(package_path)
                )
                if _has_migration_resources(installed_config):
                    return installed_config

    raise RuntimeError(
        "MeetFlow migration resources are missing from the installed distribution"
    )


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False}
            if url.startswith("sqlite")
            else {},
        )
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._configure_sqlite)

    @staticmethod
    def _configure_sqlite(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def migrate(self) -> None:
        config = Config(migration_config_path())
        config.set_main_option(
            "sqlalchemy.url",
            self.engine.url.render_as_string(hide_password=False),
        )
        command.upgrade(config, "head")

    def session(self) -> Session:
        return Session(self.engine)


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.database.session() as session:
        yield session
