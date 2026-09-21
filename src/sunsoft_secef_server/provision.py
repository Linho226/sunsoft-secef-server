import argparse
import os
import uuid

from sqlalchemy import select

from sunsoft_secef_server.storage.auth_repositories import (
    AgentCredentialRepository,
    OdooCredentialRepository,
    TenantRepository,
)
from sunsoft_secef_server.storage.database import Database
from sunsoft_secef_server.storage.models import (
    Agent,
    Tenant,
)


def _required_text(
    value: str,
    field_name: str,
) -> str:
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


def _canonical_uuid(
    value: str,
    field_name: str,
) -> str:
    normalized = _required_text(
        value,
        field_name,
    )

    try:
        parsed = uuid.UUID(
            normalized
        )
    except ValueError as exc:
        raise ValueError(
            f"{field_name} doit être un UUID valide."
        ) from exc

    canonical = str(
        parsed
    )

    if canonical != normalized.lower():
        raise ValueError(
            f"{field_name} doit être un UUID canonique."
        )

    return canonical


def provision_production(
    *,
    database: Database,
    tenant_name: str,
    agent_uid: str,
) -> dict[str, str]:
    tenant_name = _required_text(
        tenant_name,
        "tenant_name",
    )

    agent_uid = _canonical_uuid(
        agent_uid,
        "agent_uid",
    )

    with database.session() as session:
        with session.begin():
            existing_tenant = session.scalar(
                select(Tenant).where(
                    Tenant.name == tenant_name
                )
            )

            if existing_tenant is not None:
                raise RuntimeError(
                    "Un Tenant portant ce nom existe déjà."
                )

            existing_agent = session.scalar(
                select(Agent).where(
                    Agent.agent_uid == agent_uid
                )
            )

            if existing_agent is not None:
                raise RuntimeError(
                    "Cet Agent UID existe déjà."
                )

            tenant = TenantRepository(
                session
            ).create(
                name=tenant_name,
            )

            agent = Agent(
                tenant_id=tenant.id,
                agent_uid=agent_uid,
                version="0.0.0",
                environment="production",
            )

            session.add(
                agent
            )

            session.flush()

            (
                agent_credential,
                agent_token,
            ) = AgentCredentialRepository(
                session
            ).create(
                agent=agent
            )

            (
                odoo_credential,
                odoo_token,
            ) = OdooCredentialRepository(
                session
            ).create(
                tenant=tenant
            )

        return {
            "tenant_uid":
                tenant.tenant_uid,

            "agent_uid":
                agent.agent_uid,

            "agent_credential_uid":
                agent_credential.credential_uid,

            "agent_token":
                agent_token,

            "odoo_credential_uid":
                odoo_credential.credential_uid,

            "odoo_token":
                odoo_token,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Provisionnement initial "
            "Sunsoft SECeF."
        )
    )

    parser.add_argument(
        "--tenant-name",
        required=True,
        help="Nom du Tenant à provisionner.",
    )

    parser.add_argument(
        "--agent-uid",
        required=True,
        help="UID canonique de l'Agent Windows.",
    )

    args = parser.parse_args()

    database_url = (
        os.environ.get(
            "SECEF_SERVER_DATABASE_URL",
            ""
        )
        .strip()
    )

    if not database_url:
        raise RuntimeError(
            "SECEF_SERVER_DATABASE_URL "
            "n'est pas configurée."
        )

    database = Database(
        database_url
    )

    try:
        database.initialize()

        result = provision_production(
            database=database,
            tenant_name=args.tenant_name,
            agent_uid=args.agent_uid,
        )

    finally:
        database.dispose()

    print()
    print("Provisionnement SECeF terminé.")
    print()
    print(
        "Tenant UID       :",
        result["tenant_uid"],
    )
    print(
        "Agent UID        :",
        result["agent_uid"],
    )
    print(
        "Credential Agent :",
        result["agent_credential_uid"],
    )
    print(
        "Credential Odoo  :",
        result["odoo_credential_uid"],
    )

    print()
    print(
        "ATTENTION : les tokens suivants "
        "ne seront affichés qu'une seule fois."
    )
    print()

    print(
        "TOKEN ODOO  :",
        result["odoo_token"],
    )

    print(
        "TOKEN AGENT :",
        result["agent_token"],
    )


if __name__ == "__main__":
    main()
