from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./data/meetflow.db"
    data_dir: Path = Path("data")
    plugins_dir: Path = Path("plugins")
    admin_username: str = "admin"
    admin_password: str = "development-admin-password"
    app_secret_key: str = "development-secret-key-32-characters"
    allow_registration: bool = True
    secure_cookies: bool = False
    trusted_origins: str = "http://localhost:8000,http://localhost:5173"
    max_upload_bytes: int = 20 * 1024 * 1024
    plugin_timeout_seconds: float = 60.0

    @property
    def trusted_origin_set(self) -> set[str]:
        return {
            item.strip().rstrip("/")
            for item in self.trusted_origins.split(",")
            if item.strip()
        }

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            if (
                len(self.admin_password) < 12
                or self.admin_password == "development-admin-password"
            ):
                raise ValueError("ADMIN_PASSWORD must contain at least 12 characters")
            if (
                len(self.app_secret_key) < 32
                or self.app_secret_key == "development-secret-key-32-characters"
            ):
                raise ValueError("APP_SECRET_KEY must contain at least 32 characters")
            if not self.secure_cookies:
                raise ValueError("SECURE_COOKIES must be enabled in production")
            if not self.trusted_origin_set or any(
                not origin.startswith("https://")
                for origin in self.trusted_origin_set
            ):
                raise ValueError(
                    "TRUSTED_ORIGINS must contain only HTTPS origins in production"
                )
        return self
