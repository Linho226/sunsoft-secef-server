import uuid

from fastapi.testclient import TestClient

from sunsoft_secef_server.api.auth import (
    AgentAuthDependency,
    OdooAuthDependency,
)
from sunsoft_secef_server.config import (
    Settings,
)
from sunsoft_secef_server.main import (
    create_app,
)
from sunsoft_secef_server.storage.auth_repositories import (
    AgentCredentialRepository,
    OdooCredentialRepository,
    TenantRepository,
)
from sunsoft_secef_server.storage.models import (
    Agent,
)


def _new_uid() -> str:
    return str(
        uuid.uuid4()
    )


def _create_test_app(
    tmp_path,
):
    database_path = (
        tmp_path
        / "http-auth.db"
    )

    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=(
            f"sqlite:///{database_path}"
        ),
    )

    app = create_app(
        settings=settings
    )

    @app.get(
        "/_test/auth/agent"
    )
    def agent_auth_route(
        credential: AgentAuthDependency,
    ):
        return {
            "authenticated": True,
            "credential_uid":
                credential.credential_uid,
            "agent_id":
                credential.agent_id,
        }

    @app.get(
        "/_test/auth/odoo"
    )
    def odoo_auth_route(
        credential: OdooAuthDependency,
    ):
        return {
            "authenticated": True,
            "credential_uid":
                credential.credential_uid,
            "tenant_id":
                credential.tenant_id,
        }

    return app


def _provision_credentials(
    app,
):
    with (
        app.state.database.session()
        as session
    ):
        tenant = TenantRepository(
            session
        ).create(
            name="HTTP AUTH TEST",
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

        agent_credential, agent_token = (
            AgentCredentialRepository(
                session
            ).create(
                agent=agent
            )
        )

        odoo_credential, odoo_token = (
            OdooCredentialRepository(
                session
            ).create(
                tenant=tenant
            )
        )

        session.commit()

        return {
            "agent_token":
                agent_token,
            "agent_credential_uid":
                agent_credential.credential_uid,
            "agent_id":
                agent.id,
            "odoo_token":
                odoo_token,
            "odoo_credential_uid":
                odoo_credential.credential_uid,
            "tenant_id":
                tenant.id,
        }


def test_valid_agent_bearer_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        credentials = (
            _provision_credentials(
                app
            )
        )

        response = client.get(
            "/_test/auth/agent",
            headers={
                "Authorization": (
                    "Bearer "
                    f"{credentials['agent_token']}"
                ),
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert (
            body["authenticated"]
            is True
        )

        assert (
            body["credential_uid"]
            == credentials[
                "agent_credential_uid"
            ]
        )

        assert (
            body["agent_id"]
            == credentials["agent_id"]
        )


def test_valid_odoo_bearer_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        credentials = (
            _provision_credentials(
                app
            )
        )

        response = client.get(
            "/_test/auth/odoo",
            headers={
                "Authorization": (
                    "Bearer "
                    f"{credentials['odoo_token']}"
                ),
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert (
            body["authenticated"]
            is True
        )

        assert (
            body["credential_uid"]
            == credentials[
                "odoo_credential_uid"
            ]
        )

        assert (
            body["tenant_id"]
            == credentials["tenant_id"]
        )


def test_missing_agent_bearer_token_returns_401(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        response = client.get(
            "/_test/auth/agent"
        )

        assert response.status_code == 401

        assert (
            response.headers[
                "www-authenticate"
            ]
            == "Bearer"
        )


def test_missing_odoo_bearer_token_returns_401(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        response = client.get(
            "/_test/auth/odoo"
        )

        assert response.status_code == 401

        assert (
            response.headers[
                "www-authenticate"
            ]
            == "Bearer"
        )


def test_agent_endpoint_rejects_odoo_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        credentials = (
            _provision_credentials(
                app
            )
        )

        response = client.get(
            "/_test/auth/agent",
            headers={
                "Authorization": (
                    "Bearer "
                    f"{credentials['odoo_token']}"
                ),
            },
        )

        assert response.status_code == 401


def test_odoo_endpoint_rejects_agent_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        credentials = (
            _provision_credentials(
                app
            )
        )

        response = client.get(
            "/_test/auth/odoo",
            headers={
                "Authorization": (
                    "Bearer "
                    f"{credentials['agent_token']}"
                ),
            },
        )

        assert response.status_code == 401


def test_revoked_agent_token_returns_401(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        credentials = (
            _provision_credentials(
                app
            )
        )

        with (
            app.state.database.session()
            as session
        ):
            repository = (
                AgentCredentialRepository(
                    session
                )
            )

            repository.revoke(
                credentials[
                    "agent_credential_uid"
                ]
            )

            session.commit()

        response = client.get(
            "/_test/auth/agent",
            headers={
                "Authorization": (
                    "Bearer "
                    f"{credentials['agent_token']}"
                ),
            },
        )

        assert response.status_code == 401


def test_revoked_odoo_token_returns_401(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        credentials = (
            _provision_credentials(
                app
            )
        )

        with (
            app.state.database.session()
            as session
        ):
            repository = (
                OdooCredentialRepository(
                    session
                )
            )

            repository.revoke(
                credentials[
                    "odoo_credential_uid"
                ]
            )

            session.commit()

        response = client.get(
            "/_test/auth/odoo",
            headers={
                "Authorization": (
                    "Bearer "
                    f"{credentials['odoo_token']}"
                ),
            },
        )

        assert response.status_code == 401