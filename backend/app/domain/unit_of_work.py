from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session


T = TypeVar("T")


class UnitOfWork:
    """Own one command transaction without hiding session lifetime or queries."""

    def __init__(self, session: Session):
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def execute(self, command: Callable[[Session], T]) -> T:
        try:
            result = command(self.session)
            self.commit()
            return result
        except Exception:
            self.rollback()
            raise
