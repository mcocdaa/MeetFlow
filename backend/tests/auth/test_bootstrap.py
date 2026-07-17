from sqlalchemy import select

from app.auth.models import User, UserRole, UserStatus
from app.auth.service import AuthService


def test_bootstrap_creates_one_active_admin(settings, client):
    with client.app.state.database.session() as session:
        service = AuthService(settings)
        service.bootstrap_admin(session)
        service.bootstrap_admin(session)
        users = session.scalars(select(User)).all()

    assert len(users) == 1
    assert users[0].username == "admin"
    assert users[0].role == UserRole.ADMIN
    assert users[0].status == UserStatus.ACTIVE
    assert users[0].password_hash != settings.admin_password
    assert users[0].approved_by == users[0].id
