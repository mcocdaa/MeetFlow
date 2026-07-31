import pytest

from app.domain.unit_of_work import UnitOfWork


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_unit_of_work_commits_a_successful_command():
    session = FakeSession()

    result = UnitOfWork(session).execute(lambda current: (current, "ok"))

    assert result[1] == "ok"
    assert session.commits == 1
    assert session.rollbacks == 0


def test_unit_of_work_rolls_back_a_failed_command():
    session = FakeSession()

    def fail(_current):
        raise RuntimeError("snapshot failed")

    with pytest.raises(RuntimeError, match="snapshot failed"):
        UnitOfWork(session).execute(fail)

    assert session.commits == 0
    assert session.rollbacks == 1
