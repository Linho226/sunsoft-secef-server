from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)


class AgentActivationRequest(BaseModel):
    """Demande initiale de provisioning Windows."""

    model_config = ConfigDict(
        extra="forbid",
    )

    activation_code: SecretStr

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

    server_api_token: SecretStr

    @field_validator("agent_uid")
    @classmethod
    def validate_agent_uid(
        cls,
        value: str,
    ) -> str:
        try:
            return str(
                UUID(
                    value.strip()
                )
            )
        except (
            ValueError,
            AttributeError,
        ) as exc:
            raise ValueError(
                "agent_uid doit ?tre un UUID valide."
            ) from exc

    @field_validator("version")
    @classmethod
    def normalize_version(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "version ne peut pas ?tre vide."
            )

        return normalized

    @field_validator("server_api_token")
    @classmethod
    def validate_server_api_token(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        raw = (
            value.get_secret_value()
            .strip()
        )

        if (
            len(raw) < 32
            or not raw.startswith(
                "ssecf_agent_"
            )
        ):
            raise ValueError(
                "Credential Agent invalide."
            )

        return SecretStr(
            raw
        )


class AgentActivationResponse(BaseModel):
    """R?sultat d'un provisioning Agent."""

    model_config = ConfigDict(
        extra="forbid",
    )

    status: Literal["activated"]

    agent_uid: str
    tenant_uid: str

    site_uid: str
    site_code: str

    credential_uid: str

    recovered: bool
