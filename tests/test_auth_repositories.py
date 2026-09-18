import uuid

import pytest

from sunsoft_secef_server.security.tokens import (
    hash_token,
)
from sunsoft_secef_server.storage.auth_repositories import (
    AgentCredentialRepository,
    AgentTenantError,
    CredentialInactiveError,
    OdooCredentialRepository,
    TenantRepository,
)
from sunsoft_secef_server.storage.database import (
    Database,
)
from sunsoft_secef_server.storage.models import (
    Agent,
)


def _new_uid() -> str:
    return str(
        uuid.uuid4()
    )


def _create_database(
    tmp_path,
) -> Database:
    database = Database(
        f"sqlite:///{tmp_path / 'auth-repository.db'}"
    )

    database.initialize()

    return database


def _create_tenant_and_agent(
    session,
):
    tenant_repository = TenantRepository(
        session
    )

    tenant = tenant_repository.create(
        name="SUNSOFT TEST",
    )

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

    return tenant, agent


def test_tenant_repository_create_and_get(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            repository = TenantRepository(
                session
            )

            tenant = repository.create(
                name="SUNSOFT INTERNATIONAL",
            )

            found = repository.get_by_uid(
                tenant.tenant_uid
            )

            assert found is not None
            assert found.id == tenant.id

            assert (
                found.name
                == "SUNSOFT INTERNATIONAL"
            )

            assert found.is_active is True

    finally:
        database.dispose()


def test_agent_credential_authentication(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            _, agent = (
                _create_tenant_and_agent(
                    session
                )
            )

            repository = (
                AgentCredentialRepository(
                    session
                )
            )

            credential, token = (
                repository.create(
                    agent=agent
                )
            )

            assert (
                credential.token_hash
                == hash_token(token)
            )

            assert (
                credential.token_hash
                != token
            )

            authenticated = (
                repository.authenticate(
                    token
                )
            )

            assert authenticated is not None

            assert (
                authenticated.id
                == credential.id
            )

            assert (
                authenticated.agent_id
                == agent.id
            )

            assert (
                authenticated.last_used_at
                is not None
            )

    finally:
        database.dispose()


def test_wrong_agent_token_is_rejected(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            _, agent = (
                _create_tenant_and_agent(
                    session
                )
            )

            repository = (
                AgentCredentialRepository(
                    session
                )
            )

            _, token = repository.create(
                agent=agent
            )

            assert (
                repository.authenticate(
                    token + "invalid"
                )
                is None
            )

    finally:
        database.dispose()


def test_revoked_agent_token_is_rejected(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            _, agent = (
                _create_tenant_and_agent(
                    session
                )
            )

            repository = (
                AgentCredentialRepository(
                    session
                )
            )

            credential, token = (
                repository.create(
                    agent=agent
                )
            )

            repository.revoke(
                credential.credential_uid
            )

            assert credential.is_active is False
            assert credential.revoked_at is not None

            assert (
                repository.authenticate(
                    token
                )
                is None
            )

    finally:
        database.dispose()


def test_rotate_agent_credential(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            _, agent = (
                _create_tenant_and_agent(
                    session
                )
            )

            repository = (
                AgentCredentialRepository(
                    session
                )
            )

            old_credential, old_token = (
                repository.create(
                    agent=agent
                )
            )

            new_credential, new_token = (
                repository.rotate(
                    old_credential.credential_uid
                )
            )

            assert (
                old_credential.is_active
                is False
            )

            assert (
                old_credential.revoked_at
                is not None
            )

            assert (
                new_credential.id
                != old_credential.id
            )

            assert (
                new_token
                != old_token
            )

            assert (
                repository.authenticate(
                    old_token
                )
                is None
            )

            assert (
                repository.authenticate(
                    new_token
                )
                is not None
            )

    finally:
        database.dispose()


def test_agent_credential_requires_tenant(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            agent = Agent(
                agent_uid=_new_uid(),
                version="0.1.0",
                environment="test",
                tenant_id=None,
            )

            session.add(
                agent
            )

            session.flush()

            repository = (
                AgentCredentialRepository(
                    session
                )
            )

            with pytest.raises(
                AgentTenantError
            ):
                repository.create(
                    agent=agent
                )

    finally:
        database.dispose()


def test_odoo_credential_authentication(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            tenant, _ = (
                _create_tenant_and_agent(
                    session
                )
            )

            repository = (
                OdooCredentialRepository(
                    session
                )
            )

            credential, token = (
                repository.create(
                    tenant=tenant
                )
            )

            authenticated = (
                repository.authenticate(
                    token
                )
            )

            assert authenticated is not None

            assert (
                authenticated.id
                == credential.id
            )

            assert (
                authenticated.tenant_id
                == tenant.id
            )

            assert (
                authenticated.last_used_at
                is not None
            )

    finally:
        database.dispose()


def test_revoked_odoo_token_is_rejected(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            tenant, _ = (
                _create_tenant_and_agent(
                    session
                )
            )

            repository = (
                OdooCredentialRepository(
                    session
                )
            )

            credential, token = (
                repository.create(
                    tenant=tenant
                )
            )

            repository.revoke(
                credential.credential_uid
            )

            assert (
                repository.authenticate(
                    token
                )
                is None
            )

    finally:
        database.dispose()


def test_rotate_odoo_credential(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            tenant, _ = (
                _create_tenant_and_agent(
                    session
                )
            )

            repository = (
                OdooCredentialRepository(
                    session
                )
            )

            old_credential, old_token = (
                repository.create(
                    tenant=tenant
                )
            )

            new_credential, new_token = (
                repository.rotate(
                    old_credential.credential_uid
                )
            )

            assert (
                old_credential.is_active
                is False
            )

            assert (
                new_credential.id
                != old_credential.id
            )

            assert (
                repository.authenticate(
                    old_token
                )
                is None
            )

            assert (
                repository.authenticate(
                    new_token
                )
                is not None
            )

    finally:
        database.dispose()


def test_inactive_tenant_blocks_authentication(
    tmp_path,
) -> None:
    database = _create_database(
        tmp_path
    )

    try:
        with database.session() as session:
            tenant, agent = (
                _create_tenant_and_agent(
                    session
                )
            )

            agent_repository = (
                AgentCredentialRepository(
                    session
                )
            )

            odoo_repository = (
                OdooCredentialRepository(
                    session
                )
            )

            _, agent_token = (
                agent_repository.create(
                    agent=agent
                )
            )

            _, odoo_token = (
                odoo_repository.create(
                    tenant=tenant
                )
            )

            TenantRepository(
                session
            ).deactivate(
                tenant.tenant_uid
            )

            assert (
                agent_repository.authenticate(
                    agent_token
                )
                is None
            )

            assert (
                odoo_repository.authenticate(
                    odoo_token
                )
                is None
            )

    finally:
        database.dispose()