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
        / "certification-api.db"
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


def _provision_tenant_with_agent(
    app,
    *,
    agent_uid: str | None = None,
    tenant_name: str = "CERTIFICATION API TEST",
) -> dict:
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
            name=tenant_name,
        )

        agent = Agent(
            tenant_id=tenant.id,
            agent_uid=resolved_agent_uid,
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
            "tenant_id":
                tenant.id,
            "tenant_uid":
                tenant.tenant_uid,
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
        }


def _certification_payload(
    *,
    request_uid: str,
    agent_uid: str,
    invoice_number: str,
) -> dict:
    return {
        "request_uid": request_uid,
        "agent_uid": agent_uid,
        "invoice_number": invoice_number,
        "job_type": "invoice.certify",
        "payload": {
            "invoice": {
                "invoice_number":
                    invoice_number,
            },
            "customer": {
                "customer_type": "PM",
            },
            "items": [
                {
                    "name": "Produit test",
                    "quantity": "1",
                    "unit_price": "1000",
                    "amount": "1180",
                    "tax_group": "B",
                    "tax_rate": "18",
                    "item_type": "LOCBIE",
                },
            ],
            "payments": None,
        },
    }


def test_create_certification_creates_job(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    request_uid = _new_uid()
    invoice_number = (
        "INV/2026/100"
    )

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        response = client.post(
            "/api/v1/certifications",
            headers=_auth_headers(
                provisioned["odoo_token"]
            ),
            json=_certification_payload(
                request_uid=request_uid,
                agent_uid=(
                    provisioned["agent_uid"]
                ),
                invoice_number=invoice_number,
            ),
        )

        assert response.status_code == 200

        body = response.json()

        assert (
            body["request_uid"]
            == request_uid
        )

        assert (
            body["agent_uid"]
            == provisioned["agent_uid"]
        )

        assert (
            body["invoice_number"]
            == invoice_number
        )

        assert (
            body["status"]
            == "pending"
        )

        assert body["result"] is None
        assert body["error_message"] is None
        assert body["job_uid"]

        with (
            app.state.database.session()
            as session
        ):
            certification = (
                CertificationRepository(
                    session
                ).get_by_request_uid(
                    request_uid
                )
            )

            assert certification is not None

            job = (
                CentralJobRepository(
                    session
                ).get_for_certification(
                    certification.id
                )
            )

            assert job is not None

            assert (
                job.job_uid
                == body["job_uid"]
            )

            assert (
                job.status
                == JobStatus.PENDING
            )


def test_create_certification_is_idempotent(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    request_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        payload = _certification_payload(
            request_uid=request_uid,
            agent_uid=(
                provisioned["agent_uid"]
            ),
            invoice_number=(
                "INV/2026/101"
            ),
        )

        headers = _auth_headers(
            provisioned["odoo_token"]
        )

        first = client.post(
            "/api/v1/certifications",
            headers=headers,
            json=payload,
        )

        second = client.post(
            "/api/v1/certifications",
            headers=headers,
            json=payload,
        )

        assert first.status_code == 200
        assert second.status_code == 200

        assert (
            first.json()["request_uid"]
            == second.json()["request_uid"]
        )

        assert (
            first.json()["job_uid"]
            == second.json()["job_uid"]
        )


def test_create_certification_rejects_request_conflict(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    request_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        headers = _auth_headers(
            provisioned["odoo_token"]
        )

        first = client.post(
            "/api/v1/certifications",
            headers=headers,
            json=_certification_payload(
                request_uid=request_uid,
                agent_uid=(
                    provisioned["agent_uid"]
                ),
                invoice_number=(
                    "INV/2026/102"
                ),
            ),
        )

        assert first.status_code == 200

        conflicting_payload = (
            _certification_payload(
                request_uid=request_uid,
                agent_uid=(
                    provisioned["agent_uid"]
                ),
                invoice_number=(
                    "INV/2026/DIFFERENT"
                ),
            )
        )

        second = client.post(
            "/api/v1/certifications",
            headers=headers,
            json=conflicting_payload,
        )

        assert second.status_code == 409


def test_create_certification_rejects_job_type_conflict(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    request_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        headers = _auth_headers(
            provisioned["odoo_token"]
        )

        payload = _certification_payload(
            request_uid=request_uid,
            agent_uid=(
                provisioned["agent_uid"]
            ),
            invoice_number=(
                "INV/2026/103"
            ),
        )

        first = client.post(
            "/api/v1/certifications",
            headers=headers,
            json=payload,
        )

        assert first.status_code == 200

        payload["job_type"] = (
            "different.job"
        )

        second = client.post(
            "/api/v1/certifications",
            headers=headers,
            json=payload,
        )

        assert second.status_code == 409


def test_create_certification_requires_known_agent(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        response = client.post(
            "/api/v1/certifications",
            headers=_auth_headers(
                provisioned["odoo_token"]
            ),
            json=_certification_payload(
                request_uid=_new_uid(),
                agent_uid=_new_uid(),
                invoice_number=(
                    "INV/2026/104"
                ),
            ),
        )

        assert response.status_code == 404


def test_create_certification_rejects_empty_payload(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        response = client.post(
            "/api/v1/certifications",
            headers=_auth_headers(
                provisioned["odoo_token"]
            ),
            json={
                "request_uid": _new_uid(),
                "agent_uid":
                    provisioned["agent_uid"],
                "invoice_number":
                    "INV/2026/EMPTY",
                "job_type":
                    "invoice.certify",
                "payload": {},
            },
        )

        assert response.status_code == 422


def test_get_certification_returns_pending_status(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    request_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        headers = _auth_headers(
            provisioned["odoo_token"]
        )

        create_response = client.post(
            "/api/v1/certifications",
            headers=headers,
            json=_certification_payload(
                request_uid=request_uid,
                agent_uid=(
                    provisioned["agent_uid"]
                ),
                invoice_number=(
                    "INV/2026/105"
                ),
            ),
        )

        assert (
            create_response.status_code
            == 200
        )

        response = client.get(
            (
                "/api/v1/certifications/"
                f"{request_uid}"
            ),
            headers=headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert (
            body["request_uid"]
            == request_uid
        )

        assert (
            body["status"]
            == "pending"
        )

        assert (
            body["job_uid"]
            == create_response.json()[
                "job_uid"
            ]
        )


def test_get_unknown_certification_returns_404(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        response = client.get(
            (
                "/api/v1/certifications/"
                f"{_new_uid()}"
            ),
            headers=_auth_headers(
                provisioned["odoo_token"]
            ),
        )

        assert response.status_code == 404


def test_get_certification_returns_completed_result(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    request_uid = _new_uid()

    invoice_number = (
        "INV/2026/106"
    )

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        odoo_headers = _auth_headers(
            provisioned["odoo_token"]
        )

        agent_headers = _auth_headers(
            provisioned["agent_token"]
        )

        create_response = client.post(
            "/api/v1/certifications",
            headers=odoo_headers,
            json=_certification_payload(
                request_uid=request_uid,
                agent_uid=(
                    provisioned["agent_uid"]
                ),
                invoice_number=invoice_number,
            ),
        )

        assert (
            create_response.status_code
            == 200
        )

        job_uid = (
            create_response.json()[
                "job_uid"
            ]
        )

        result = {
            "invoice_number":
                invoice_number,
            "mid":
                "DT02200630-1",
            "ifu":
                "00225673B",
            "signature":
                "ODOOTEST001",
            "datetime":
                "20260918170000",
            "invoice_counter":
                301,
            "total_counter":
                401,
            "qr_data": (
                "BFSECEF01;"
                "DT02200630-1;"
                "ODOOTEST001;"
                "00225673B;"
                "20260918170000"
            ),
        }

        report_response = client.put(
            (
                f"/api/v1/agents/"
                f"{provisioned['agent_uid']}"
                "/jobs/"
                f"{job_uid}/status"
            ),
            headers=agent_headers,
            json={
                "status": "completed",
                "attempt_count": 1,
                "result": result,
                "error_message": None,
            },
        )

        assert (
            report_response.status_code
            == 200
        )

        response = client.get(
            (
                "/api/v1/certifications/"
                f"{request_uid}"
            ),
            headers=odoo_headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert (
            body["status"]
            == "completed"
        )

        assert (
            body["result"]
            == result
        )

        assert (
            body["error_message"]
            is None
        )


def test_get_certification_returns_unknown_status(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    request_uid = _new_uid()

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        odoo_headers = _auth_headers(
            provisioned["odoo_token"]
        )

        agent_headers = _auth_headers(
            provisioned["agent_token"]
        )

        create_response = client.post(
            "/api/v1/certifications",
            headers=odoo_headers,
            json=_certification_payload(
                request_uid=request_uid,
                agent_uid=(
                    provisioned["agent_uid"]
                ),
                invoice_number=(
                    "INV/2026/107"
                ),
            ),
        )

        assert (
            create_response.status_code
            == 200
        )

        job_uid = (
            create_response.json()[
                "job_uid"
            ]
        )

        report_response = client.put(
            (
                f"/api/v1/agents/"
                f"{provisioned['agent_uid']}"
                "/jobs/"
                f"{job_uid}/status"
            ),
            headers=agent_headers,
            json={
                "status": "unknown",
                "attempt_count": 1,
                "result": None,
                "error_message": (
                    "Résultat fiscal indéterminé."
                ),
            },
        )

        assert (
            report_response.status_code
            == 200
        )

        response = client.get(
            (
                "/api/v1/certifications/"
                f"{request_uid}"
            ),
            headers=odoo_headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert (
            body["status"]
            == "unknown"
        )

        assert body["result"] is None

        assert (
            body["error_message"]
            == (
                "Résultat fiscal indéterminé."
            )
        )


# ---------------------------------------------------------
# Tests de sécurité Odoo / Tenant
# ---------------------------------------------------------


def test_create_certification_requires_odoo_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        response = client.post(
            "/api/v1/certifications",
            json=_certification_payload(
                request_uid=_new_uid(),
                agent_uid=(
                    provisioned["agent_uid"]
                ),
                invoice_number=(
                    "INV/2026/AUTH-001"
                ),
            ),
        )

        assert response.status_code == 401


def test_create_certification_rejects_agent_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        response = client.post(
            "/api/v1/certifications",
            headers=_auth_headers(
                provisioned["agent_token"]
            ),
            json=_certification_payload(
                request_uid=_new_uid(),
                agent_uid=(
                    provisioned["agent_uid"]
                ),
                invoice_number=(
                    "INV/2026/AUTH-002"
                ),
            ),
        )

        assert response.status_code == 401


def test_create_certification_rejects_other_tenant_agent(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        tenant_a = (
            _provision_tenant_with_agent(
                app,
                tenant_name="TENANT A",
            )
        )

        tenant_b = (
            _provision_tenant_with_agent(
                app,
                tenant_name="TENANT B",
            )
        )

        response = client.post(
            "/api/v1/certifications",
            headers=_auth_headers(
                tenant_a["odoo_token"]
            ),
            json=_certification_payload(
                request_uid=_new_uid(),
                agent_uid=(
                    tenant_b["agent_uid"]
                ),
                invoice_number=(
                    "INV/2026/CROSS-TENANT"
                ),
            ),
        )

        assert response.status_code == 403


def test_get_certification_requires_odoo_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        response = client.get(
            (
                "/api/v1/certifications/"
                f"{_new_uid()}"
            )
        )

        assert response.status_code == 401


def test_get_certification_rejects_agent_token(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    with TestClient(app) as client:
        provisioned = (
            _provision_tenant_with_agent(
                app
            )
        )

        response = client.get(
            (
                "/api/v1/certifications/"
                f"{_new_uid()}"
            ),
            headers=_auth_headers(
                provisioned["agent_token"]
            ),
        )

        assert response.status_code == 401


def test_tenant_cannot_read_other_tenant_certification(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    request_uid = _new_uid()

    with TestClient(app) as client:
        tenant_a = (
            _provision_tenant_with_agent(
                app,
                tenant_name="TENANT A",
            )
        )

        tenant_b = (
            _provision_tenant_with_agent(
                app,
                tenant_name="TENANT B",
            )
        )

        create_response = client.post(
            "/api/v1/certifications",
            headers=_auth_headers(
                tenant_b["odoo_token"]
            ),
            json=_certification_payload(
                request_uid=request_uid,
                agent_uid=(
                    tenant_b["agent_uid"]
                ),
                invoice_number=(
                    "INV/2026/TENANT-B"
                ),
            ),
        )

        assert (
            create_response.status_code
            == 200
        )

        response = client.get(
            (
                "/api/v1/certifications/"
                f"{request_uid}"
            ),
            headers=_auth_headers(
                tenant_a["odoo_token"]
            ),
        )

        # On masque volontairement l'existence
        # d'une certification appartenant à B.
        assert response.status_code == 404