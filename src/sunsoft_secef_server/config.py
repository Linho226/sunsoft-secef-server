from functools import lru_cache
from typing import Literal

from pydantic import Field
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

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Retourne la configuration globale du serveur."""

    return Settings()
