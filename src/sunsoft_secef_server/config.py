from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """Configuration du serveur central SECeF."""

    model_config = SettingsConfigDict(
        env_prefix="SECEF_SERVER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal[
        "development",
        "test",
        "production",
    ] = "development"

    host: str = "127.0.0.1"

    port: int = Field(
        default=9000,
        ge=1,
        le=65535,
    )

    database_url: str = (
        "sqlite:///server_data/server.db"
    )

    log_level: str = "INFO"

    # --------------------------------------------------
    # Interface Web d'administration
    # --------------------------------------------------

    admin_enabled: bool = False

    admin_username: str = "admin"

    admin_password_hash: str | None = None

    admin_session_secret: SecretStr | None = None

    admin_session_https_only: bool = True

    admin_session_max_age_seconds: int = Field(
        default=28800,
        ge=300,
        le=86400,
    )


    # --------------------------------------------------
    # Distribution Agent Windows
    # --------------------------------------------------

    agent_release_storage_dir: str = (
        "server_data/releases/agent"
    )

    agent_release_max_upload_bytes: int = Field(
        default=536870912,
        ge=1048576,
        le=2147483648,
    )


@lru_cache
def get_settings() -> Settings:
    """Retourne la configuration globale du serveur."""

    return Settings()