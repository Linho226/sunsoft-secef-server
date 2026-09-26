from pathlib import Path
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from sunsoft_secef_server.api.dependencies import (
    get_session,
)
from sunsoft_secef_server.api.routes.agents import (
    router as agents_router,
)
from sunsoft_secef_server.security.tokens import (
    generate_agent_token,
)
from sunsoft_secef_server.storage.auth_repositories import (
    AgentActivationCodeRepository,
    SiteRepository,
    TenantRepository,
)
from sunsoft_secef_server.storage.database import (
    Database,
)
from sunsoft_secef_server.storage.models import (
    Agent,
    AgentActivationCode,
    AgentCredential,
    utc_now,
)


AGENT_UID = (
    "22222222-2222-4222-8222-222222222222"
)


def _build_database(
    tmp_path: Path,
) -> Database:
    path = tmp_path / "activation-api.db"

    database = Database(
        f"sqlite:///{path.as_posix()}"
    )

    database.initialize()

    return database


def _build_app(
    database: Database,
) -> FastAPI:
    app = FastAPI()

    app.include_router(
        agents_router,
        prefix="/api/v1",
    )

    def override_get_session():
        session = database.session()

        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[
        get_session
    ] = override_get_session

    return app


def _prepare_activation(
    database: Database,
):
    session = database.session()

    try:
        tenant = TenantRepository(
            session
        ).create(
            name="CLIENT ACTIVATION TEST",
        )

        site = SiteRepository(
            session
        ).create(
            tenant=tenant,
            code="SIEGE",
            name="Siège",
        )

        activation, code = (
            AgentActivationCodeRepository(
                session
            ).create(
                tenant=tenant,
                site=site,
                expires_in_minutes=60,
            )
        )

        session.commit()

        return {
            "tenant_id": tenant.id,
            "tenant_uid": tenant.tenant_uid,
            "site_id": site.id,
            "site_uid": site.site_uid,
            "activation_id": activation.id,
            "activation_code": code,
        }

    finally:
        session.close()


def _activation_payload(
    code: str,
    token: str,
) -> dict[str, str]:
    return {
        "activation_code": code,
        "agent_uid": AGENT_UID,
        "version": "1.0.0",
        "environment": "production",
        "server_api_token": token,
    }


def test_activation_is_idempotent_and_heartbeat_works(
    tmp_path: Path,
) -> None:
    database = _build_database(
        tmp_path
    )

    try:
        provisioning = _prepare_activation(
            database
        )

        agent_token = (
            generate_agent_token()
        )

        app = _build_app(
            database
        )

        payload = _activation_payload(
            provisioning[
                "activation_code"
            ],
            agent_token,
        )

        with TestClient(app) as client:

            first = client.post(
                "/api/v1/agents/activate",
                json=payload,
            )

            assert first.status_code == 200

            first_body = first.json()

            assert (
                first_body["status"]
                == "activated"
            )

            assert (
                first_body["recovered"]
                is False
            )

            second = client.post(
                "/api/v1/agents/activate",
                json=payload,
            )

            assert second.status_code == 200

            second_body = second.json()

            assert (
                second_body["recovered"]
                is True
            )

            assert (
                second_body["credential_uid"]
                == first_body["credential_uid"]
            )

            heartbeat = client.put(
                (
                    "/api/v1/agents/"
                    f"{AGENT_UID}/heartbeat"
                ),
                headers={
                    "Authorization":
                        f"Bearer {agent_token}",
                },
                json={
                    "agent_uid": AGENT_UID,
                    "version": "1.0.0",
                    "environment": "production",
                },
            )

            assert heartbeat.status_code == 200

        session = database.session()

        try:
            assert session.scalar(
                select(
                    func.count(
                        Agent.id
                    )
                )
            ) == 1

            assert session.scalar(
                select(
                    func.count(
                        AgentCredential.id
                    )
                )
            ) == 1

            agent = session.scalar(
                select(
                    Agent
                ).where(
                    Agent.agent_uid
                    == AGENT_UID
                )
            )

            assert agent is not None

            assert (
                agent.site_id
                == provisioning["site_id"]
            )

            activation = session.get(
                AgentActivationCode,
                provisioning[
                    "activation_id"
                ],
            )

            assert activation is not None

            assert (
                activation.used_by_agent_id
                == agent.id
            )

        finally:
            session.close()

    finally:
        database.dispose()


def test_used_code_rejects_different_token(
    tmp_path: Path,
) -> None:
    database = _build_database(
        tmp_path
    )

    try:
        provisioning = _prepare_activation(
            database
        )

        app = _build_app(
            database
        )

        original_token = (
            generate_agent_token()
        )

        with TestClient(app) as client:

            first = client.post(
                "/api/v1/agents/activate",
                json=_activation_payload(
                    provisioning[
                        "activation_code"
                    ],
                    original_token,
                ),
            )

            assert first.status_code == 200

            replay = client.post(
                "/api/v1/agents/activate",
                json=_activation_payload(
                    provisioning[
                        "activation_code"
                    ],
                    generate_agent_token(),
                ),
            )

            assert replay.status_code == 409

        session = database.session()

        try:
            assert session.scalar(
                select(
                    func.count(
                        AgentCredential.id
                    )
                )
            ) == 1

        finally:
            session.close()

    finally:
        database.dispose()


def test_unused_expired_code_is_rejected(
    tmp_path: Path,
) -> None:
    database = _build_database(
        tmp_path
    )

    try:
        provisioning = _prepare_activation(
            database
        )

        session = database.session()

        try:
            activation = session.get(
                AgentActivationCode,
                provisioning[
                    "activation_id"
                ],
            )

            assert activation is not None

            activation.expires_at = (
                utc_now()
                - timedelta(
                    minutes=1
                )
            )

            session.commit()

        finally:
            session.close()

        app = _build_app(
            database
        )

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/agents/activate",
                json=_activation_payload(
                    provisioning[
                        "activation_code"
                    ],
                    generate_agent_token(),
                ),
            )

        assert response.status_code == 409

    finally:
        database.dispose()


def test_completed_activation_can_recover_after_expiry(
    tmp_path: Path,
) -> None:
    database = _build_database(
        tmp_path
    )

    try:
        provisioning = _prepare_activation(
            database
        )

        token = generate_agent_token()

        app = _build_app(
            database
        )

        payload = _activation_payload(
            provisioning[
                "activation_code"
            ],
            token,
        )

        with TestClient(app) as client:
            first = client.post(
                "/api/v1/agents/activate",
                json=payload,
            )

            assert first.status_code == 200

        session = database.session()

        try:
            activation = session.get(
                AgentActivationCode,
                provisioning[
                    "activation_id"
                ],
            )

            assert activation is not None

            activation.expires_at = (
                utc_now()
                - timedelta(
                    hours=1
                )
            )

            session.commit()

        finally:
            session.close()

        with TestClient(app) as client:
            recovery = client.post(
                "/api/v1/agents/activate",
                json=payload,
            )

        assert recovery.status_code == 200
        assert (
            recovery.json()["recovered"]
            is True
        )

    finally:
        database.dispose()
