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