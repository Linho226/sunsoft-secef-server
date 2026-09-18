from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class AgentHeartbeatRequest(BaseModel):
    """Heartbeat reçu depuis un Agent SECeF."""

    model_config = ConfigDict(
        extra="forbid"
    )

    agent_uid: str = Field(
        min_length=36,
        max_length=36,
    )

    version: str = Field(
        min_length=1,
        max_length=50,
    )

    environment: Literal[
        "development",
        "test",
        "production",
    ]


class AgentHeartbeatResponse(BaseModel):
    """Accusé de réception du heartbeat Agent."""

    model_config = ConfigDict(
        extra="forbid"
    )

    status: str = Field(
        min_length=1,
        max_length=50,
    )

    agent_uid: str = Field(
        min_length=36,
        max_length=36,
    )


class CentralJob(BaseModel):
    """Job transmis par le serveur central à un Agent."""

    model_config = ConfigDict(
        extra="forbid"
    )

    job_uid: str = Field(
        min_length=1,
        max_length=128,
    )

    job_type: str = Field(
        min_length=1,
        max_length=100,
    )

    payload: dict[str, Any]

    @field_validator(
        "job_uid",
        "job_type",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: str,
    ) -> str:
        """Normalise les identifiants obligatoires."""

        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError(
                "La valeur ne peut pas être vide."
            )

        return normalized_value


class CentralJobReportRequest(BaseModel):
    """État d'un Job remonté par un Agent."""

    model_config = ConfigDict(
        extra="forbid"
    )

    status: Literal[
        "pending",
        "processing",
        "completed",
        "failed",
        "unknown",
    ]

    attempt_count: int = Field(
        ge=0,
    )

    result: dict[str, Any] | None = None

    error_message: str | None = Field(
        default=None,
        max_length=4000,
    )

    @field_validator(
        "error_message",
    )
    @classmethod
    def normalize_error_message(
        cls,
        value: str | None,
    ) -> str | None:
        """Normalise le message d'erreur."""

        if value is None:
            return None

        normalized_value = value.strip()

        return normalized_value or None


class CentralJobReportResponse(BaseModel):
    """Accusé de réception d'un rapport de Job."""

    model_config = ConfigDict(
        extra="forbid"
    )

    status: Literal[
        "accepted",
    ]

    agent_uid: str = Field(
        min_length=36,
        max_length=36,
    )

    job_uid: str = Field(
        min_length=1,
        max_length=128,
    )

    @field_validator(
        "job_uid",
    )
    @classmethod
    def normalize_job_uid(
        cls,
        value: str,
    ) -> str:
        """Normalise l'identifiant du Job."""

        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError(
                "Le job_uid ne peut pas être vide."
            )

        return normalized_value
