import uuid

from fastapi.testclient import TestClient

from sunsoft_secef_server.config import Settings
from sunsoft_secef_server.main import create_app
from sunsoft_secef_server.storage.auth_repositories import (
    AgentCredentialRepository,
    OdooCredentialRepository,
    TenantRepository,
)
from sunsoft_secef_server.storage.models import (
    Agent,
    JobStatus,
)
from sunsoft_secef_server.storage.repositories import (
    AgentRepository,
    CentralJobRepository,
    CertificationRepository,
)


def _new_uid() -> str:
    return str(uuid.uuid4())


def _create_test_app(
    tmp_path,
):
    database_path = (
        tmp_path
        / "central-api.db"
    )

    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=(
            f"sqlite:///{database_path}"
        ),
    )

    return create_app(
        settings=settings
    )


def _auth_headers(
    token: str,
) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {token}"
        ),
    }


def _provision_agent(
    app,
    *,
    agent_uid: str | None = None,
) -> dict:
    """
    Crée un Tenant, un Agent et ses credentials.

    Cela simule le provisioning réalisé avant le
    premier démarrage de l'Agent Windows.
    """

    resolved_agent_uid = (
        agent_uid
        if agent_uid is not None
        else _new_uid()
    )

    with (
        app.state.database.session()
        as session
    ):
        tenant = TenantRepository(
            session
        ).create(
            name="AGENT API TEST",
        )

        agent = Agent(
            tenant_id=tenant.id,
            agent_uid=resolved_agent_uid,
            version="0.0.0",
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
            "agent_uid":
                resolved_agent_uid,
            "agent_id":
                agent.id,
            "agent_token":
                agent_token,
            "agent_credential_uid":
                agent_credential.credential_uid,
            "odoo_token":
                odoo_token,
            "odoo_credential_uid":
                odoo_credential.credential_uid,
            "tenant_id":
                tenant.id,
        }


def _create_job(
    app,
    *,
    agent_uid: str,
    invoice_number: str,
) -> dict:
    request_uid = _new_uid()
    job_uid = _new_uid()

    payload = {
        "invoice": {
            "invoice_number":
                invoice_number,
        },
    }

    with (
        app.state.database.session()
        as session
    ):
        agent = AgentRepository(
            session
        ).get_by_uid(
            agent_uid
        )

        assert agent is not None

        certification, _ = (
            CertificationRepository(
                session
            ).create_or_get(
                request_uid=request_uid,
                agent_uid=agent_uid,
                invoice_number=invoice_number,
                payload=payload,
            )
        )

        CentralJobRepository(
            session
        ).create_or_get(
            job_uid=job_uid,
            certification_request=(
                certification
            ),
            agent=agent,
            job_type="invoice.certify",
            payload=payload,
        )

        session.commit()

    return {
        "request_uid": request_uid,
        "job_uid": job_uid,
        "payload": payload,
    }


def test_heartbeat_updates_provisioned_agent(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app,
            agent_uid=agent_uid,
        )

        response = client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
            ),
            headers=_auth_headers(
                provisioned["agent_token"]
            ),
            json={
                "agent_uid": agent_uid,
                "version": "0.1.0",
                "environment": "test",
            },
        )

        assert response.status_code == 200

        assert response.json() == {
            "status": "accepted",
            "agent_uid": agent_uid,
        }

        with (
            app.state.database.session()
            as session
        ):
            agent = AgentRepository(
                session
            ).get_by_uid(
                agent_uid
            )

            assert agent is not None
            assert agent.version == "0.1.0"
            assert agent.environment == "test"


def test_heartbeat_rejects_uid_mismatch(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    path_uid = _new_uid()
    payload_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app,
            agent_uid=path_uid,
        )

        response = client.put(
            (
                f"/api/v1/agents/"
                f"{path_uid}/heartbeat"
            ),
            headers=_auth_headers(
                provisioned["agent_token"]
            ),
            json={
                "agent_uid": payload_uid,
                "version": "0.1.0",
                "environment": "test",
            },
        )

        assert response.status_code == 409


def test_agent_route_requires_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()

    with TestClient(app) as client:
        _provision_agent(
            app,
            agent_uid=agent_uid,
        )

        response = client.get(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/jobs/next"
            )
        )

        assert response.status_code == 401

        assert (
            response.headers[
                "www-authenticate"
            ]
            == "Bearer"
        )


def test_agent_route_rejects_odoo_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app,
            agent_uid=agent_uid,
        )

        response = client.get(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/jobs/next"
            ),
            headers=_auth_headers(
                provisioned["odoo_token"]
            ),
        )

        assert response.status_code == 401


def test_agent_cannot_access_another_agent(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        agent_a = _provision_agent(
            app
        )

        agent_b = _provision_agent(
            app
        )

        response = client.get(
            (
                f"/api/v1/agents/"
                f"{agent_b['agent_uid']}"
                "/jobs/next"
            ),
            headers=_auth_headers(
                agent_a["agent_token"]
            ),
        )

        assert response.status_code == 403


def test_revoked_agent_token_is_rejected(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app
        )

        with (
            app.state.database.session()
            as session
        ):
            AgentCredentialRepository(
                session
            ).revoke(
                provisioned[
                    "agent_credential_uid"
                ]
            )

            session.commit()

        response = client.get(
            (
                f"/api/v1/agents/"
                f"{provisioned['agent_uid']}"
                "/jobs/next"
            ),
            headers=_auth_headers(
                provisioned["agent_token"]
            ),
        )

        assert response.status_code == 401


def test_next_job_returns_no_content(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app
        )

        response = client.get(
            (
                f"/api/v1/agents/"
                f"{provisioned['agent_uid']}"
                "/jobs/next"
            ),
            headers=_auth_headers(
                provisioned["agent_token"]
            ),
        )

        assert response.status_code == 204
        assert response.content == b""


def test_next_job_returns_expected_job(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app
        )

        created = _create_job(
            app,
            agent_uid=(
                provisioned["agent_uid"]
            ),
            invoice_number=(
                "INV/2026/001"
            ),
        )

        response = client.get(
            (
                f"/api/v1/agents/"
                f"{provisioned['agent_uid']}"
                "/jobs/next"
            ),
            headers=_auth_headers(
                provisioned["agent_token"]
            ),
        )

        assert response.status_code == 200

        assert response.json() == {
            "job_uid":
                created["job_uid"],
            "job_type":
                "invoice.certify",
            "payload":
                created["payload"],
        }


def test_report_completed_updates_central_state(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app
        )

        created = _create_job(
            app,
            agent_uid=(
                provisioned["agent_uid"]
            ),
            invoice_number=(
                "INV/2026/002"
            ),
        )

        result = {
            "invoice_number":
                "INV/2026/002",
            "mid":
                "DT02200630-1",
            "ifu":
                "00225673B",
            "signature":
                "TEST001",
            "datetime":
                "20260918150000",
            "invoice_counter":
                10,
            "total_counter":
                20,
            "qr_data": (
                "BFSECEF01;"
                "DT02200630-1;"
                "TEST001;"
                "00225673B;"
                "20260918150000"
            ),
        }

        response = client.put(
            (
                f"/api/v1/agents/"
                f"{provisioned['agent_uid']}"
                "/jobs/"
                f"{created['job_uid']}"
                "/status"
            ),
            headers=_auth_headers(
                provisioned["agent_token"]
            ),
            json={
                "status": "completed",
                "attempt_count": 1,
                "result": result,
                "error_message": None,
            },
        )

        assert response.status_code == 200

        assert response.json() == {
            "status": "accepted",
            "agent_uid":
                provisioned["agent_uid"],
            "job_uid":
                created["job_uid"],
        }

        with (
            app.state.database.session()
            as session
        ):
            job = CentralJobRepository(
                session
            ).get_by_uid(
                created["job_uid"]
            )

            certification = (
                CertificationRepository(
                    session
                ).get_by_request_uid(
                    created["request_uid"]
                )
            )

            assert job is not None
            assert certification is not None

            assert (
                job.status
                == JobStatus.COMPLETED
            )

            assert (
                certification.status
                == JobStatus.COMPLETED
            )

            assert job.result == result

            assert (
                certification.result
                == result
            )


def test_agent_cannot_report_another_agents_job(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        agent_a = _provision_agent(
            app
        )

        agent_b = _provision_agent(
            app
        )

        job_b = _create_job(
            app,
            agent_uid=agent_b["agent_uid"],
            invoice_number=(
                "INV/2026/OTHER-AGENT"
            ),
        )

        response = client.put(
            (
                f"/api/v1/agents/"
                f"{agent_a['agent_uid']}"
                "/jobs/"
                f"{job_b['job_uid']}"
                "/status"
            ),
            headers=_auth_headers(
                agent_a["agent_token"]
            ),
            json={
                "status": "completed",
                "attempt_count": 1,
                "result": {
                    "test": True,
                },
                "error_message": None,
            },
        )

        assert response.status_code == 404


def test_heartbeat_persists_and_updates_mcf_status(
    tmp_path,
) -> None:
    """
    Le heartbeat cr?e puis met ? jour une seule
    ligne agent_mcf_status pour l'Agent.
    """

    from sqlalchemy import (
        func,
        select,
    )

    from sunsoft_secef_server.storage.models import (
        AgentMCFStatus,
    )

    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app,
            agent_uid=agent_uid,
        )

        headers = _auth_headers(
            provisioned["agent_token"]
        )

        first = client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
            ),
            headers=headers,
            json={
                "agent_uid": agent_uid,
                "version": "0.1.0",
                "environment": "test",
                "mcf_status": {
                    "sent_transactions": 12,
                    "available_transactions": 88,
                    "last_connection_datetime": (
                        "20261116093000"
                    ),
                    "connection_age_seconds": 3600,
                    "connection_stale": False,
                    "last_error": None,
                },
            },
        )

        assert first.status_code == 200

        with (
            app.state.database.session()
            as session
        ):
            agent = AgentRepository(
                session
            ).get_by_uid(
                agent_uid
            )

            assert agent is not None

            first_status = session.scalar(
                select(
                    AgentMCFStatus
                ).where(
                    AgentMCFStatus.agent_id
                    == agent.id
                )
            )

            assert first_status is not None

            first_status_id = (
                first_status.id
            )

            assert (
                first_status.sent_transactions
                == 12
            )

            assert (
                first_status.available_transactions
                == 88
            )

            assert (
                first_status.last_connection_datetime
                == "20261116093000"
            )

            assert (
                first_status.connection_age_seconds
                == 3600
            )

            assert (
                first_status.connection_stale
                is False
            )

        second = client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
            ),
            headers=headers,
            json={
                "agent_uid": agent_uid,
                "version": "0.2.0",
                "environment": "test",
                "mcf_status": {
                    "sent_transactions": 15,
                    "available_transactions": 85,
                    "last_connection_datetime": (
                        "20261116103000"
                    ),
                    "connection_age_seconds": 120,
                    "connection_stale": False,
                    "last_error": "E42",
                },
            },
        )

        assert second.status_code == 200

        with (
            app.state.database.session()
            as session
        ):
            agent = AgentRepository(
                session
            ).get_by_uid(
                agent_uid
            )

            assert agent is not None

            status = session.scalar(
                select(
                    AgentMCFStatus
                ).where(
                    AgentMCFStatus.agent_id
                    == agent.id
                )
            )

            assert status is not None

            assert status.id == first_status_id

            assert (
                status.sent_transactions
                == 15
            )

            assert (
                status.available_transactions
                == 85
            )

            assert (
                status.last_connection_datetime
                == "20261116103000"
            )

            assert (
                status.connection_age_seconds
                == 120
            )

            assert (
                status.connection_stale
                is False
            )

            assert status.last_error == "E42"

            count = session.scalar(
                select(
                    func.count(
                        AgentMCFStatus.id
                    )
                ).where(
                    AgentMCFStatus.agent_id
                    == agent.id
                )
            )

            assert count == 1


def test_heartbeat_without_mcf_status_preserves_existing_status(
    tmp_path,
) -> None:
    """
    Un heartbeat historique sans mcf_status
    ne supprime ni n'alt?re le dernier statut C2h.
    """

    from sqlalchemy import select

    from sunsoft_secef_server.storage.models import (
        AgentMCFStatus,
    )

    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app,
            agent_uid=agent_uid,
        )

        headers = _auth_headers(
            provisioned["agent_token"]
        )

        with_status = client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
            ),
            headers=headers,
            json={
                "agent_uid": agent_uid,
                "version": "0.1.0",
                "environment": "test",
                "mcf_status": {
                    "sent_transactions": 7,
                    "available_transactions": 93,
                    "last_connection_datetime": (
                        "20261116080000"
                    ),
                    "connection_age_seconds": 7200,
                    "connection_stale": False,
                    "last_error": None,
                },
            },
        )

        assert with_status.status_code == 200

        legacy = client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
            ),
            headers=headers,
            json={
                "agent_uid": agent_uid,
                "version": "0.2.0",
                "environment": "production",
            },
        )

        assert legacy.status_code == 200

        with (
            app.state.database.session()
            as session
        ):
            agent = AgentRepository(
                session
            ).get_by_uid(
                agent_uid
            )

            assert agent is not None

            status = session.scalar(
                select(
                    AgentMCFStatus
                ).where(
                    AgentMCFStatus.agent_id
                    == agent.id
                )
            )

            assert status is not None

            assert (
                status.sent_transactions
                == 7
            )

            assert (
                status.available_transactions
                == 93
            )

            assert (
                status.last_connection_datetime
                == "20261116080000"
            )

            assert (
                status.connection_age_seconds
                == 7200
            )

            assert (
                status.connection_stale
                is False
            )

            assert status.last_error is None

            # Le heartbeat Agent reste bien actualis?.
            assert agent.version == "0.2.0"

            assert (
                agent.environment
                == "production"
            )



def test_agent_odoo_status_lifecycle(
    tmp_path,
) -> None:
    """
    Le statut Odoo suit la presence du credential
    du Tenant de l'Agent.
    """

    from datetime import timedelta

    from sunsoft_secef_server.storage.auth_repositories import (
        OdooCredentialRepository,
    )
    from sunsoft_secef_server.storage.models import (
        utc_now,
    )

    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = _provision_agent(
            app,
            agent_uid=agent_uid,
        )

        agent_headers = _auth_headers(
            provisioned["agent_token"]
        )

        endpoint = (
            f"/api/v1/agents/"
            f"{agent_uid}/odoo-status"
        )

        # Credential cree, mais aucun heartbeat Odoo.
        initial = client.get(
            endpoint,
            headers=agent_headers,
        )

        assert initial.status_code == 200

        initial_body = initial.json()

        assert (
            initial_body["status"]
            == "unavailable"
        )
        assert (
            initial_body[
                "credential_configured"
            ]
            is True
        )
        assert (
            initial_body["last_seen_at"]
            is None
        )
        assert (
            initial_body[
                "stale_after_seconds"
            ]
            == 180
        )

        # Simule une presence Odoo recente.
        with (
            app.state.database.session()
            as session
        ):
            repository = (
                OdooCredentialRepository(
                    session
                )
            )

            odoo_credential = (
                repository.get_by_uid(
                    provisioned[
                        "odoo_credential_uid"
                    ]
                )
            )

            assert odoo_credential is not None

            odoo_credential.last_used_at = (
                utc_now()
            )

            session.commit()

        linked = client.get(
            endpoint,
            headers=agent_headers,
        )

        assert linked.status_code == 200

        linked_body = linked.json()

        assert (
            linked_body["status"]
            == "linked"
        )
        assert (
            linked_body["last_seen_at"]
            is not None
        )
        assert (
            linked_body[
                "last_seen_age_seconds"
            ]
            is not None
        )
        assert (
            linked_body[
                "last_seen_age_seconds"
            ]
            <= 180
        )

        # Simule plus de trois minutes
        # sans activite Odoo.
        with (
            app.state.database.session()
            as session
        ):
            repository = (
                OdooCredentialRepository(
                    session
                )
            )

            odoo_credential = (
                repository.get_by_uid(
                    provisioned[
                        "odoo_credential_uid"
                    ]
                )
            )

            assert odoo_credential is not None

            odoo_credential.last_used_at = (
                utc_now()
                - timedelta(
                    minutes=4
                )
            )

            session.commit()

        stale = client.get(
            endpoint,
            headers=agent_headers,
        )

        assert stale.status_code == 200

        stale_body = stale.json()

        assert (
            stale_body["status"]
            == "unavailable"
        )
        assert (
            stale_body[
                "credential_configured"
            ]
            is True
        )
        assert (
            stale_body[
                "last_seen_age_seconds"
            ]
            > 180
        )

        # Credential revoque :
        # plus aucune liaison Odoo active.
        with (
            app.state.database.session()
            as session
        ):
            OdooCredentialRepository(
                session
            ).revoke(
                provisioned[
                    "odoo_credential_uid"
                ]
            )

            session.commit()

        unlinked = client.get(
            endpoint,
            headers=agent_headers,
        )

        assert unlinked.status_code == 200

        unlinked_body = (
            unlinked.json()
        )

        assert (
            unlinked_body["status"]
            == "not_linked"
        )
        assert (
            unlinked_body[
                "credential_configured"
            ]
            is False
        )
        assert (
            unlinked_body["last_seen_at"]
            is None
        )
