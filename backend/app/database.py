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


def migration_config_path() -> Path:
    source_config = Path(__file__).resolve().parents[1] / "alembic.ini"
    if source_config.is_file():
        return source_config

    try:
        installed_config = Path(
            distribution("meetflow").locate_file("share/meetflow/alembic.ini")
        )
    except PackageNotFoundError:
        installed_config = Path()
    if installed_config.is_file():
        return installed_config

    raise RuntimeError("MeetFlow migration resources are not installed")


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
