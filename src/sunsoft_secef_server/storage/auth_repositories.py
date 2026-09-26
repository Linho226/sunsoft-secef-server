import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sunsoft_secef_server.security.activation import (
    InvalidActivationCodeError,
    generate_activation_code,
    hash_activation_code,
)
from sunsoft_secef_server.security.tokens import (
    InvalidTokenError,
    generate_agent_token,
    generate_odoo_token,
    get_token_kind,
    hash_token,
)
from sunsoft_secef_server.storage.models import (
    Agent,
    AgentActivationCode,
    AgentCredential,
    OdooCredential,
    Site,
    Tenant,
    utc_now,
)


class AuthRepositoryError(RuntimeError):
    """Erreur générique de persistance d'authentification."""


class TenantNotFoundError(AuthRepositoryError):
    """Tenant introuvable."""


class ActivationCodeError(AuthRepositoryError):
    """Erreur de provisioning par code d'activation."""


class ActivationCodeUnavailableError(
    ActivationCodeError
):
    """
    Code invalide, expir?, d?sactiv?
    ou d?j? consomm?.
    """


class SiteNotFoundError(AuthRepositoryError):
    """Site introuvable."""


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


class SiteRepository:
    """Gestion des Sites rattach?s aux Tenants."""

    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_uid(
        self,
        site_uid: str,
    ) -> Site | None:
        normalized_uid = _normalize_required_text(
            site_uid,
            "site_uid",
        )

        statement = select(Site).where(
            Site.site_uid == normalized_uid
        )

        return self.session.scalar(
            statement
        )

    def require_by_uid(
        self,
        site_uid: str,
    ) -> Site:
        site = self.get_by_uid(
            site_uid
        )

        if site is None:
            raise SiteNotFoundError(
                "Site introuvable."
            )

        return site

    def get_by_code(
        self,
        *,
        tenant: Tenant,
        code: str,
    ) -> Site | None:
        if tenant.id is None:
            raise TenantNotFoundError(
                "Le Tenant doit ?tre persist?."
            )

        normalized_code = (
            _normalize_required_text(
                code,
                "code",
            )
            .upper()
        )

        statement = select(Site).where(
            Site.tenant_id == tenant.id,
            Site.code == normalized_code,
        )

        return self.session.scalar(
            statement
        )

    def list_by_tenant(
        self,
        tenant: Tenant,
    ) -> list[Site]:
        if tenant.id is None:
            raise TenantNotFoundError(
                "Le Tenant doit ?tre persist?."
            )

        statement = (
            select(Site)
            .where(
                Site.tenant_id == tenant.id
            )
            .order_by(
                Site.name,
                Site.id,
            )
        )

        return list(
            self.session.scalars(
                statement
            )
        )

    def create(
        self,
        *,
        tenant: Tenant,
        code: str,
        name: str,
        site_uid: str | None = None,
    ) -> Site:
        if tenant.id is None:
            raise TenantNotFoundError(
                "Le Tenant doit ?tre persist?."
            )

        if not tenant.is_active:
            raise AuthRepositoryError(
                "Le Tenant est inactif."
            )

        normalized_code = (
            _normalize_required_text(
                code,
                "code",
            )
            .upper()
        )

        normalized_name = _normalize_required_text(
            name,
            "name",
        )

        normalized_uid = (
            _normalize_required_text(
                site_uid,
                "site_uid",
            )
            if site_uid is not None
            else _new_uid()
        )

        if self.get_by_uid(
            normalized_uid
        ) is not None:
            raise AuthRepositoryError(
                "Le site_uid existe d?j?."
            )

        if self.get_by_code(
            tenant=tenant,
            code=normalized_code,
        ) is not None:
            raise AuthRepositoryError(
                "Le code Site existe d?j? "
                "pour ce Tenant."
            )

        site = Site(
            tenant_id=tenant.id,
            site_uid=normalized_uid,
            code=normalized_code,
            name=normalized_name,
            is_active=True,
        )

        self.session.add(
            site
        )

        self.session.flush()

        return site

    def deactivate(
        self,
        site_uid: str,
    ) -> Site:
        site = self.require_by_uid(
            site_uid
        )

        site.is_active = False

        self.session.flush()

        return site


class AgentActivationCodeRepository:
    """
    Gestion des codes ? usage unique destin?s
    au provisioning des Agents Windows.
    """

    DEFAULT_EXPIRATION_MINUTES = 60
    MAX_EXPIRATION_MINUTES = 1440

    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_uid(
        self,
        activation_uid: str,
    ) -> AgentActivationCode | None:
        normalized_uid = _normalize_required_text(
            activation_uid,
            "activation_uid",
        )

        statement = select(
            AgentActivationCode
        ).where(
            AgentActivationCode.activation_uid
            == normalized_uid
        )

        return self.session.scalar(
            statement
        )

    def get_by_code(
        self,
        code: str,
    ) -> AgentActivationCode | None:
        try:
            code_hash = hash_activation_code(
                code
            )
        except (
            InvalidActivationCodeError,
            TypeError,
        ):
            return None

        statement = select(
            AgentActivationCode
        ).where(
            AgentActivationCode.code_hash
            == code_hash
        )

        return self.session.scalar(
            statement
        )

    def create(
        self,
        *,
        tenant: Tenant,
        site: Site,
        expires_in_minutes: int = (
            DEFAULT_EXPIRATION_MINUTES
        ),
    ) -> tuple[
        AgentActivationCode,
        str,
    ]:
        if tenant.id is None:
            raise TenantNotFoundError(
                "Le Tenant doit ?tre persist?."
            )

        if site.id is None:
            raise SiteNotFoundError(
                "Le Site doit ?tre persist?."
            )

        if not tenant.is_active:
            raise ActivationCodeError(
                "Le Tenant est inactif."
            )

        if not site.is_active:
            raise ActivationCodeError(
                "Le Site est inactif."
            )

        if site.tenant_id != tenant.id:
            raise ActivationCodeError(
                "Le Site n'appartient pas "
                "au Tenant."
            )

        if (
            isinstance(
                expires_in_minutes,
                bool,
            )
            or not isinstance(
                expires_in_minutes,
                int,
            )
            or expires_in_minutes <= 0
            or expires_in_minutes
            > self.MAX_EXPIRATION_MINUTES
        ):
            raise ValueError(
                "expires_in_minutes doit ?tre "
                "compris entre 1 et 1440."
            )

        # Une collision est extr?mement improbable,
        # mais la boucle rend l'op?ration robuste.
        for _ in range(5):
            raw_code = generate_activation_code()

            code_hash = hash_activation_code(
                raw_code
            )

            existing = self.session.scalar(
                select(
                    AgentActivationCode.id
                ).where(
                    AgentActivationCode.code_hash
                    == code_hash
                )
            )

            if existing is None:
                break
        else:
            raise ActivationCodeError(
                "Impossible de g?n?rer "
                "un code unique."
            )

        activation = AgentActivationCode(
            activation_uid=_new_uid(),
            tenant_id=tenant.id,
            site_id=site.id,
            code_hash=code_hash,
            expires_at=(
                utc_now()
                + timedelta(
                    minutes=expires_in_minutes
                )
            ),
            used_at=None,
            used_by_agent_id=None,
            is_active=True,
        )

        self.session.add(
            activation
        )

        self.session.flush()

        # Le code brut sort une seule fois.
        return activation, raw_code

    def revoke(
        self,
        activation_uid: str,
    ) -> AgentActivationCode:
        """
        R?voque un code d'activation non consomm?.
        """

        activation = self.get_by_uid(
            activation_uid
        )

        if activation is None:
            raise ActivationCodeError(
                "Code d'activation introuvable."
            )

        if activation.used_at is not None:
            raise ActivationCodeError(
                "Un code d?j? consomm? "
                "ne peut pas ?tre r?voqu?."
            )

        if not activation.is_active:
            return activation

        activation.is_active = False

        self.session.flush()

        return activation


    def claim(
        self,
        code: str,
    ) -> AgentActivationCode:
        """
        Consomme atomiquement un code encore valide.

        PostgreSQL garantit ici qu'un seul appel
        concurrent peut passer de actif ? consomm?.
        """

        try:
            code_hash = hash_activation_code(
                code
            )
        except (
            InvalidActivationCodeError,
            TypeError,
        ) as exc:
            raise ActivationCodeUnavailableError(
                "Code d'activation indisponible."
            ) from exc

        now = utc_now()

        statement = (
            update(
                AgentActivationCode
            )
            .where(
                AgentActivationCode.code_hash
                == code_hash,
                AgentActivationCode.is_active
                .is_(True),
                AgentActivationCode.used_at
                .is_(None),
                AgentActivationCode.expires_at
                > now,
            )
            .values(
                is_active=False,
                used_at=now,
            )
            .returning(
                AgentActivationCode.id
            )
        )

        activation_id = self.session.scalar(
            statement
        )

        if activation_id is None:
            raise ActivationCodeUnavailableError(
                "Code d'activation indisponible."
            )

        self.session.flush()

        activation = self.session.get(
            AgentActivationCode,
            activation_id,
        )

        if activation is None:
            raise ActivationCodeUnavailableError(
                "Code d'activation indisponible."
            )

        return activation

    def recover_for_agent(
        self,
        *,
        code: str,
        agent_uid: str,
    ) -> tuple[
        AgentActivationCode,
        Agent,
    ] | None:
        """
        Autorise uniquement la reprise d'une activation
        d?j? termin?e pour le m?me Agent.

        Cette reprise sert notamment si la r?ponse HTTP
        de l'activation initiale a ?t? perdue.
        """

        try:
            code_hash = hash_activation_code(
                code
            )
        except (
            InvalidActivationCodeError,
            TypeError,
        ):
            return None

        normalized_agent_uid = (
            _normalize_required_text(
                agent_uid,
                "agent_uid",
            )
        )

        now = utc_now()

        statement = (
            select(
                AgentActivationCode,
                Agent,
            )
            .join(
                Agent,
                AgentActivationCode.used_by_agent_id
                == Agent.id,
            )
            .where(
                AgentActivationCode.code_hash
                == code_hash,
                AgentActivationCode.is_active
                .is_(False),
                AgentActivationCode.used_at
                .is_not(None),
                Agent.agent_uid
                == normalized_agent_uid,
            )
            .with_for_update()
        )

        row = self.session.execute(
            statement
        ).first()

        if row is None:
            return None

        return row[0], row[1]

    def bind_agent(
        self,
        *,
        activation: AgentActivationCode,
        agent: Agent,
    ) -> AgentActivationCode:
        """
        Associe au code consomm? l'Agent
        effectivement provisionn?.
        """

        if activation.id is None:
            raise ActivationCodeError(
                "Activation non persist?e."
            )

        if activation.used_at is None:
            raise ActivationCodeError(
                "Le code doit ?tre consomm? "
                "avant association."
            )

        if agent.id is None:
            raise ActivationCodeError(
                "L'Agent doit ?tre persist?."
            )

        if (
            agent.tenant_id
            != activation.tenant_id
        ):
            raise ActivationCodeError(
                "Tenant Agent incompatible."
            )

        if (
            agent.site_id
            != activation.site_id
        ):
            raise ActivationCodeError(
                "Site Agent incompatible."
            )

        activation.used_by_agent_id = (
            agent.id
        )

        self.session.flush()

        return activation


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

    def provision_with_token(
        self,
        *,
        agent: Agent,
        token: str,
        replace_existing: bool,
    ) -> AgentCredential:
        """
        Enregistre le hash d'un token g?n?r? c?t? Agent.

        Si exactement le m?me token est rejou? pour
        le m?me Agent, l'op?ration est idempotente.
        """

        self._require_valid_agent(
            agent
        )

        try:
            if get_token_kind(token) != "agent":
                raise InvalidTokenError(
                    "Type de token invalide."
                )

            token_hash = hash_token(
                token
            )

        except (
            InvalidTokenError,
            TypeError,
        ) as exc:
            raise AuthRepositoryError(
                "Credential Agent invalide."
            ) from exc

        existing = self.session.scalar(
            select(
                AgentCredential
            ).where(
                AgentCredential.token_hash
                == token_hash
            )
        )

        if existing is not None:
            if (
                existing.agent_id != agent.id
                or not existing.is_active
                or existing.revoked_at is not None
            ):
                raise AuthRepositoryError(
                    "Credential Agent indisponible."
                )

            # Rejeu exact : aucun nouveau credential.
            return existing

        active_credentials = list(
            self.session.scalars(
                select(
                    AgentCredential
                ).where(
                    AgentCredential.agent_id
                    == agent.id,
                    AgentCredential.is_active
                    .is_(True),
                    AgentCredential.revoked_at
                    .is_(None),
                )
            )
        )

        if (
            active_credentials
            and not replace_existing
        ):
            raise AuthRepositoryError(
                "Un credential diff?rent existe "
                "d?j? pour cet Agent."
            )

        if replace_existing:
            now = utc_now()

            for credential in active_credentials:
                credential.is_active = False
                credential.revoked_at = now

        credential = AgentCredential(
            credential_uid=_new_uid(),
            agent_id=agent.id,
            token_hash=token_hash,
            is_active=True,
        )

        self.session.add(
            credential
        )

        self.session.flush()

        return credential


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