from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


Environment = Literal[
    "development",
    "test",
    "production",
]

JobStatusValue = Literal[
    "pending",
    "processing",
    "completed",
    "failed",
    "unknown",
]


def _normalize_required_text(
    value: str,
    field_name: str,
) -> str:
    """Normalise une chaîne obligatoire."""

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(
            f"{field_name} ne peut pas être vide."
        )

    return normalized_value


class AgentHeartbeatRequest(BaseModel):
    """Heartbeat reçu depuis un Agent SECeF."""

    model_config = ConfigDict(
        extra="forbid",
    )

    agent_uid: str = Field(
        min_length=36,
        max_length=36,
    )

    version: str = Field(
        min_length=1,
        max_length=50,
    )

    environment: Environment

    @field_validator(
        "agent_uid",
        "version",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: str,
        info,
    ) -> str:
        return _normalize_required_text(
            value,
            info.field_name,
        )


class AgentHeartbeatResponse(BaseModel):
    """Accusé de réception du heartbeat Agent."""

    model_config = ConfigDict(
        extra="forbid",
    )

    status: Literal["accepted"]

    agent_uid: str = Field(
        min_length=36,
        max_length=36,
    )

    @field_validator(
        "agent_uid",
    )
    @classmethod
    def normalize_agent_uid(
        cls,
        value: str,
    ) -> str:
        return _normalize_required_text(
            value,
            "agent_uid",
        )


class CentralJob(BaseModel):
    """Job transmis par le serveur central à un Agent."""

    model_config = ConfigDict(
        extra="forbid",
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
        info,
    ) -> str:
        return _normalize_required_text(
            value,
            info.field_name,
        )

    @field_validator(
        "payload",
    )
    @classmethod
    def validate_payload(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not value:
            raise ValueError(
                "payload ne peut pas être vide."
            )

        return value


class CentralJobReportRequest(BaseModel):
    """État d'un Job remonté par un Agent."""

    model_config = ConfigDict(
        extra="forbid",
    )

    status: JobStatusValue

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
        if value is None:
            return None

        normalized_value = value.strip()

        return normalized_value or None


class CentralJobReportResponse(BaseModel):
    """Accusé de réception d'un rapport de Job."""

    model_config = ConfigDict(
        extra="forbid",
    )

    status: Literal["accepted"]

    agent_uid: str = Field(
        min_length=36,
        max_length=36,
    )

    job_uid: str = Field(
        min_length=1,
        max_length=128,
    )

    @field_validator(
        "agent_uid",
        "job_uid",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: str,
        info,
    ) -> str:
        return _normalize_required_text(
            value,
            info.field_name,
        )


class CertificationCreateRequest(BaseModel):
    """Demande de certification reçue depuis Odoo."""

    model_config = ConfigDict(
        extra="forbid",
    )

    request_uid: str = Field(
        min_length=1,
        max_length=128,
    )

    agent_uid: str = Field(
        min_length=36,
        max_length=36,
    )

    invoice_number: str = Field(
        min_length=1,
        max_length=128,
    )

    job_type: str = Field(
        default="invoice.certify",
        min_length=1,
        max_length=100,
    )

    payload: dict[str, Any]

    @field_validator(
        "request_uid",
        "agent_uid",
        "invoice_number",
        "job_type",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: str,
        info,
    ) -> str:
        return _normalize_required_text(
            value,
            info.field_name,
        )

    @field_validator(
        "payload",
    )
    @classmethod
    def validate_payload(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not value:
            raise ValueError(
                "payload ne peut pas être vide."
            )

        return value


class CertificationResponse(BaseModel):
    """État central d'une demande de certification."""

    model_config = ConfigDict(
        extra="forbid",
    )

    request_uid: str = Field(
        min_length=1,
        max_length=128,
    )

    job_uid: str = Field(
        min_length=1,
        max_length=128,
    )

    agent_uid: str = Field(
        min_length=36,
        max_length=36,
    )

    invoice_number: str = Field(
        min_length=1,
        max_length=128,
    )

    status: JobStatusValue

    result: dict[str, Any] | None = None

    error_message: str | None = Field(
        default=None,
        max_length=4000,
    )

    @field_validator(
        "request_uid",
        "job_uid",
        "agent_uid",
        "invoice_number",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: str,
        info,
    ) -> str:
        return _normalize_required_text(
            value,
            info.field_name,
        )

    @field_validator(
        "error_message",
    )
    @classmethod
    def normalize_error_message(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized_value = value.strip()

        return normalized_value or None