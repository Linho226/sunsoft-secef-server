import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from sunsoft_secef_server.security.tokens import (
    InvalidTokenError,
    generate_agent_token,
    generate_odoo_token,
    get_token_kind,
    hash_token,
)
from sunsoft_secef_server.storage.models import (
    Agent,
    AgentCredential,
    OdooCredential,
    Tenant,
    utc_now,
)


class AuthRepositoryError(RuntimeError):
    """Erreur générique de persistance d'authentification."""


class TenantNotFoundError(AuthRepositoryError):
    """Tenant introuvable."""


class CredentialNotFoundError(AuthRepositoryError):
    """Credential introuvable."""


class CredentialInactiveError(AuthRepositoryError):
    """Credential révoqué ou inactif."""


class AgentTenantError(AuthRepositoryError):
    """Agent non rattaché à un Tenant valide."""


def _normalize_required_text(
    value: str,
    field_name: str,
) -> str:
    """Normalise une chaîne obligatoire."""

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} doit être une chaîne."
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{field_name} ne peut pas être vide."
        )

    return normalized


def _new_uid() -> str:
    """Génère un identifiant UUID canonique."""

    return str(
        uuid.uuid4()
    )


class TenantRepository:
    """Gestion des Tenants de la plateforme centrale."""

    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_uid(
        self,
        tenant_uid: str,
    ) -> Tenant | None:
        normalized_uid = _normalize_required_text(
            tenant_uid,
            "tenant_uid",
        )

        statement = select(Tenant).where(
            Tenant.tenant_uid == normalized_uid
        )

        return self.session.scalar(
            statement
        )

    def require_by_uid(
        self,
        tenant_uid: str,
    ) -> Tenant:
        tenant = self.get_by_uid(
            tenant_uid
        )

        if tenant is None:
            raise TenantNotFoundError(
                "Tenant introuvable."
            )

        return tenant

    def create(
        self,
        *,
        name: str,
        tenant_uid: str | None = None,
    ) -> Tenant:
        normalized_name = _normalize_required_text(
            name,
            "name",
        )

        normalized_uid = (
            _normalize_required_text(
                tenant_uid,
                "tenant_uid",
            )
            if tenant_uid is not None
            else _new_uid()
        )

        existing = self.get_by_uid(
            normalized_uid
        )

        if existing is not None:
            raise AuthRepositoryError(
                "Le tenant_uid existe déjà."
            )

        tenant = Tenant(
            tenant_uid=normalized_uid,
            name=normalized_name,
            is_active=True,
        )

        self.session.add(
            tenant
        )

        self.session.flush()

        return tenant

    def deactivate(
        self,
        tenant_uid: str,
    ) -> Tenant:
        tenant = self.require_by_uid(
            tenant_uid
        )

        tenant.is_active = False

        self.session.flush()

        return tenant


class AgentCredentialRepository:
    """Gestion des credentials des Agents Windows."""

    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_uid(
        self,
        credential_uid: str,
    ) -> AgentCredential | None:
        normalized_uid = _normalize_required_text(
            credential_uid,
            "credential_uid",
        )

        statement = select(
            AgentCredential
        ).where(
            AgentCredential.credential_uid
            == normalized_uid
        )

        return self.session.scalar(
            statement
        )

    def require_by_uid(
        self,
        credential_uid: str,
    ) -> AgentCredential:
        credential = self.get_by_uid(
            credential_uid
        )

        if credential is None:
            raise CredentialNotFoundError(
                "Credential Agent introuvable."
            )

        return credential

    def _require_valid_agent(
        self,
        agent: Agent,
    ) -> Tenant:
        if agent.id is None:
            raise AgentTenantError(
                "L'Agent doit être persisté."
            )

        if agent.tenant_id is None:
            raise AgentTenantError(
                "L'Agent n'est rattaché "
                "à aucun Tenant."
            )

        tenant = self.session.get(
            Tenant,
            agent.tenant_id,
        )

        if tenant is None:
            raise AgentTenantError(
                "Le Tenant de l'Agent "
                "est introuvable."
            )

        if not tenant.is_active:
            raise AgentTenantError(
                "Le Tenant de l'Agent est inactif."
            )

        return tenant

    def create(
        self,
        *,
        agent: Agent,
    ) -> tuple[
        AgentCredential,
        str,
    ]:
        """
        Crée un credential Agent.

        Le token brut est retourné une seule fois.
        Seule son empreinte est persistée.
        """

        self._require_valid_agent(
            agent
        )

        token = generate_agent_token()

        credential = AgentCredential(
            credential_uid=_new_uid(),
            agent_id=agent.id,
            token_hash=hash_token(
                token
            ),
            is_active=True,
        )

        self.session.add(
            credential
        )

        self.session.flush()

        return credential, token

    def authenticate(
        self,
        token: str,
    ) -> AgentCredential | None:
        """
        Résout un Bearer token vers son Agent.

        Retourne None lorsque le token est inconnu,
        invalide, révoqué ou lié à un Tenant inactif.
        """

        try:
            if get_token_kind(token) != "agent":
                return None

            token_hash = hash_token(
                token
            )

        except (
            InvalidTokenError,
            TypeError,
        ):
            return None

        statement = (
            select(AgentCredential)
            .join(
                Agent,
                AgentCredential.agent_id
                == Agent.id,
            )
            .join(
                Tenant,
                Agent.tenant_id
                == Tenant.id,
            )
            .where(
                AgentCredential.token_hash
                == token_hash,
                AgentCredential.is_active.is_(
                    True
                ),
                AgentCredential.revoked_at.is_(
                    None
                ),
                Tenant.is_active.is_(
                    True
                ),
            )
        )

        credential = self.session.scalar(
            statement
        )

        if credential is None:
            return None

        credential.last_used_at = utc_now()

        self.session.flush()

        return credential

    def revoke(
        self,
        credential_uid: str,
    ) -> AgentCredential:
        """Révoque un credential Agent."""

        credential = self.require_by_uid(
            credential_uid
        )

        if not credential.is_active:
            return credential

        credential.is_active = False

        if credential.revoked_at is None:
            credential.revoked_at = utc_now()

        self.session.flush()

        return credential

    def rotate(
        self,
        credential_uid: str,
    ) -> tuple[
        AgentCredential,
        str,
    ]:
        """
        Remplace un credential Agent.

        Le nouveau token est créé avant la révocation
        logique de l'ancien dans la même transaction.
        """

        old_credential = self.require_by_uid(
            credential_uid
        )

        if (
            not old_credential.is_active
            or old_credential.revoked_at
            is not None
        ):
            raise CredentialInactiveError(
                "Le credential Agent "
                "est déjà inactif."
            )

        agent = self.session.get(
            Agent,
            old_credential.agent_id,
        )

        if agent is None:
            raise AgentTenantError(
                "Agent du credential introuvable."
            )

        new_credential, token = self.create(
            agent=agent
        )

        old_credential.is_active = False
        old_credential.revoked_at = utc_now()

        self.session.flush()

        return new_credential, token


class OdooCredentialRepository:
    """Gestion des credentials des instances Odoo."""

    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_uid(
        self,
        credential_uid: str,
    ) -> OdooCredential | None:
        normalized_uid = _normalize_required_text(
            credential_uid,
            "credential_uid",
        )

        statement = select(
            OdooCredential
        ).where(
            OdooCredential.credential_uid
            == normalized_uid
        )

        return self.session.scalar(
            statement
        )

    def require_by_uid(
        self,
        credential_uid: str,
    ) -> OdooCredential:
        credential = self.get_by_uid(
            credential_uid
        )

        if credential is None:
            raise CredentialNotFoundError(
                "Credential Odoo introuvable."
            )

        return credential

    def create(
        self,
        *,
        tenant: Tenant,
    ) -> tuple[
        OdooCredential,
        str,
    ]:
        """
        Crée un credential Odoo.

        Le token brut est retourné une seule fois.
        """

        if tenant.id is None:
            raise TenantNotFoundError(
                "Le Tenant doit être persisté."
            )

        if not tenant.is_active:
            raise CredentialInactiveError(
                "Le Tenant est inactif."
            )

        token = generate_odoo_token()

        credential = OdooCredential(
            credential_uid=_new_uid(),
            tenant_id=tenant.id,
            token_hash=hash_token(
                token
            ),
            is_active=True,
        )

        self.session.add(
            credential
        )

        self.session.flush()

        return credential, token

    def authenticate(
        self,
        token: str,
    ) -> OdooCredential | None:
        """
        Résout un Bearer token vers son Tenant.

        Les credentials révoqués et les Tenants
        désactivés sont automatiquement refusés.
        """

        try:
            if get_token_kind(token) != "odoo":
                return None

            token_hash = hash_token(
                token
            )

        except (
            InvalidTokenError,
            TypeError,
        ):
            return None

        statement = (
            select(OdooCredential)
            .join(
                Tenant,
                OdooCredential.tenant_id
                == Tenant.id,
            )
            .where(
                OdooCredential.token_hash
                == token_hash,
                OdooCredential.is_active.is_(
                    True
                ),
                OdooCredential.revoked_at.is_(
                    None
                ),
                Tenant.is_active.is_(
                    True
                ),
            )
        )

        credential = self.session.scalar(
            statement
        )

        if credential is None:
            return None

        credential.last_used_at = utc_now()

        self.session.flush()

        return credential

    def revoke(
        self,
        credential_uid: str,
    ) -> OdooCredential:
        """Révoque un credential Odoo."""

        credential = self.require_by_uid(
            credential_uid
        )

        if not credential.is_active:
            return credential

        credential.is_active = False

        if credential.revoked_at is None:
            credential.revoked_at = utc_now()

        self.session.flush()

        return credential

    def rotate(
        self,
        credential_uid: str,
    ) -> tuple[
        OdooCredential,
        str,
    ]:
        """Remplace un credential Odoo."""

        old_credential = self.require_by_uid(
            credential_uid
        )

        if (
            not old_credential.is_active
            or old_credential.revoked_at
            is not None
        ):
            raise CredentialInactiveError(
                "Le credential Odoo "
                "est déjà inactif."
            )

        tenant = self.session.get(
            Tenant,
            old_credential.tenant_id,
        )

        if tenant is None:
            raise TenantNotFoundError(
                "Tenant du credential introuvable."
            )

        new_credential, token = self.create(
            tenant=tenant
        )

        old_credential.is_active = False
        old_credential.revoked_at = utc_now()

        self.session.flush()

        return new_credential, token