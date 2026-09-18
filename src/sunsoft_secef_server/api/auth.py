from typing import Annotated, NoReturn

from fastapi import (
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from sunsoft_secef_server.api.dependencies import (
    SessionDependency,
)
from sunsoft_secef_server.storage.auth_repositories import (
    AgentCredentialRepository,
    OdooCredentialRepository,
)
from sunsoft_secef_server.storage.models import (
    AgentCredential,
    OdooCredential,
)


bearer_scheme = HTTPBearer(
    auto_error=False,
)


BearerCredentialsDependency = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]


def _raise_unauthorized() -> NoReturn:
    """
    Retourne volontairement une erreur générique.

    Nous ne révélons pas si le token est inexistant,
    révoqué, lié à un Tenant inactif ou du mauvais type.
    """

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Authentification Bearer requise "
            "ou identifiants invalides."
        ),
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def _extract_bearer_token(
    credentials: (
        HTTPAuthorizationCredentials
        | None
    ),
) -> str:
    """Extrait un Bearer token valide."""

    if credentials is None:
        _raise_unauthorized()

    if (
        credentials.scheme.strip().lower()
        != "bearer"
    ):
        _raise_unauthorized()

    token = credentials.credentials.strip()

    if not token:
        _raise_unauthorized()

    return token


def require_agent_credential(
    credentials: BearerCredentialsDependency,
    session: SessionDependency,
) -> AgentCredential:
    """
    Authentifie un Agent Windows.

    Un token Odoo ne peut pas être utilisé comme
    credential Agent.
    """

    token = _extract_bearer_token(
        credentials
    )

    credential = (
        AgentCredentialRepository(
            session
        ).authenticate(
            token
        )
    )

    if credential is None:
        _raise_unauthorized()

    return credential


def require_odoo_credential(
    credentials: BearerCredentialsDependency,
    session: SessionDependency,
) -> OdooCredential:
    """
    Authentifie une instance Odoo.

    Un token Agent ne peut pas être utilisé comme
    credential Odoo.
    """

    token = _extract_bearer_token(
        credentials
    )

    credential = (
        OdooCredentialRepository(
            session
        ).authenticate(
            token
        )
    )

    if credential is None:
        _raise_unauthorized()

    return credential


AgentAuthDependency = Annotated[
    AgentCredential,
    Depends(require_agent_credential),
]


OdooAuthDependency = Annotated[
    OdooCredential,
    Depends(require_odoo_credential),
]