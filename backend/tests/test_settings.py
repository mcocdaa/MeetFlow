import pytest
from pydantic import ValidationError

from app.config import Settings


def production_settings(**overrides):
    values = {
        "app_env": "production",
        "admin_password": "strong-admin-password",
        "app_secret_key": "a-production-secret-key-with-32-chars",
        "secure_cookies": True,
        "trusted_origins": "https://meetflow.example.com",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("field", "placeholder"),
    [
        ("admin_password", "change-this-admin-password"),
        (
            "app_secret_key",
            "change-this-random-secret-before-use-0001",
        ),
    ],
)
def test_production_rejects_documented_placeholder_secrets(field, placeholder):
    with pytest.raises(ValidationError):
        production_settings(**{field: placeholder})
