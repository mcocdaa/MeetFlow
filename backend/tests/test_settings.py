from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPOSITORY_ROOT / ".env.example"


def env_example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip()
    return values


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


def test_production_requires_secure_cookies_and_https_origins():
    with pytest.raises(ValidationError):
        production_settings(secure_cookies=False)
    with pytest.raises(ValidationError):
        production_settings(trusted_origins="http://meetflow.example.com")


def test_env_example_is_a_production_template_that_requires_editing():
    values = env_example_values()
    assert values["app_env"] == "production"
    with pytest.raises(ValidationError):
        Settings(**values)
