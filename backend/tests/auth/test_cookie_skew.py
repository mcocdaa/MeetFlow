from time import time

from app.auth.service import AuthService


class _FakeUser:
    id = "u1"
    session_version = 1


def test_read_cookie_tolerates_small_clock_skew_into_the_future(settings, monkeypatch):
    service = AuthService(settings)
    future = time() + 5
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: future)
    token = service.issue_cookie(_FakeUser())
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: time())
    assert service.read_cookie(token) == ("u1", 1)


def test_read_cookie_rejects_far_future_token(settings, monkeypatch):
    service = AuthService(settings)
    future = time() + 3600
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: future)
    token = service.issue_cookie(_FakeUser())
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: time())
    assert service.read_cookie(token) is None


def test_read_cookie_rejects_expired_token(settings, monkeypatch):
    service = AuthService(settings)
    past = time() - service.cookie_max_age - 10
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: past)
    token = service.issue_cookie(_FakeUser())
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: time())
    assert service.read_cookie(token) is None


def test_read_cookie_rejects_tampered_token(settings):
    service = AuthService(settings)
    assert service.read_cookie("forged.token.payload") is None
