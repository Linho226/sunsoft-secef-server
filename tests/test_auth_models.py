import uuid

from sqlalchemy import inspect, select

from sunsoft_secef_server.security.tokens import (
    generate_agent_token,
    generate_odoo_token,
    hash_token,
)
from sunsoft_secef_server.storage.database import (
    Database,
)
from sunsoft_secef_server.storage.models import (
    Agent,
    AgentCredential,
    OdooCredential,
    Tenant,
)


def _new_uid() -> str:
    return str(
        uuid.uuid4()
    )


def test_authentication_tables_exist(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'auth.db'}"
    )

    database.initialize()

    try:
        inspector = inspect(
            database.engine
        )

        tables = set(
            inspector.get_table_names()
        )

        assert "tenants" in tables
        assert "agents" in tables

        assert (
            "odoo_credentials"
            in tables
        )

        assert (
            "agent_credentials"
            in tables
        )

    finally:
        database.dispose()


def test_tenant_agent_and_credentials_are_persisted(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'auth.db'}"
    )

    database.initialize()

    agent_token = (
        generate_agent_token()
    )

    odoo_token = (
        generate_odoo_token()
    )

    try:
        with database.session() as session:
            tenant = Tenant(
                tenant_uid=_new_uid(),
                name="SUNSOFT TEST",
            )

            session.add(
                tenant
            )

            session.flush()

            agent = Agent(
                tenant_id=tenant.id,
                agent_uid=_new_uid(),
                version="0.1.0",
                environment="test",
            )

            session.add(
                agent
            )

            session.flush()

            agent_credential = (
                AgentCredential(
                    credential_uid=_new_uid(),
                    agent_id=agent.id,
                    token_hash=hash_token(
                        agent_token
                    ),
                )
            )

            odoo_credential = (
                OdooCredential(
                    credential_uid=_new_uid(),
                    tenant_id=tenant.id,
                    token_hash=hash_token(
                        odoo_token
                    ),
                )
            )

            session.add_all(
                [
                    agent_credential,
                    odoo_credential,
                ]
            )

            session.commit()

            agent_id = agent.id
            tenant_id = tenant.id

        with database.session() as session:
            stored_agent = session.scalar(
                select(Agent).where(
                    Agent.id == agent_id
                )
            )

            stored_tenant = session.scalar(
                select(Tenant).where(
                    Tenant.id == tenant_id
                )
            )

            assert stored_agent is not None
            assert stored_tenant is not None

            assert (
                stored_agent.tenant_id
                == stored_tenant.id
            )

            assert (
                len(
                    stored_agent.credentials
                )
                == 1
            )

            assert (
                len(
                    stored_tenant.odoo_credentials
                )
                == 1
            )

            assert (
                stored_agent.credentials[
                    0
                ].token_hash
                == hash_token(
                    agent_token
                )
            )

            assert (
                stored_tenant.odoo_credentials[
                    0
                ].token_hash
                == hash_token(
                    odoo_token
                )
            )

    finally:
        database.dispose()


def test_plaintext_tokens_are_not_stored(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'auth.db'}"
    )

    database.initialize()

    token = generate_odoo_token()

    try:
        with database.session() as session:
            tenant = Tenant(
                tenant_uid=_new_uid(),
                name="TOKEN STORAGE TEST",
            )

            session.add(
                tenant
            )

            session.flush()

            credential = OdooCredential(
                credential_uid=_new_uid(),
                tenant_id=tenant.id,
                token_hash=hash_token(
                    token
                ),
            )

            session.add(
                credential
            )

            session.commit()

            credential_id = (
                credential.id
            )

        with database.session() as session:
            stored = session.get(
                OdooCredential,
                credential_id,
            )

            assert stored is not None

            assert (
                stored.token_hash
                != token
            )

            assert (
                stored.token_hash
                == hash_token(token)
            )

    finally:
        database.dispose()