import uuid

from fastapi.testclient import TestClient

from sunsoft_secef_server.config import Settings
from sunsoft_secef_server.main import create_app
from sunsoft_secef_server.storage.models import (
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


def test_heartbeat_registers_agent(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()

    with TestClient(app) as client:
        response = client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
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
        response = client.put(
            (
                f"/api/v1/agents/"
                f"{path_uid}/heartbeat"
            ),
            json={
                "agent_uid": payload_uid,
                "version": "0.1.0",
                "environment": "test",
            },
        )

        assert response.status_code == 409


def test_next_job_returns_no_content(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()

    with TestClient(app) as client:
        heartbeat_response = client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
            ),
            json={
                "agent_uid": agent_uid,
                "version": "0.1.0",
                "environment": "test",
            },
        )

        assert (
            heartbeat_response.status_code
            == 200
        )

        response = client.get(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/jobs/next"
            )
        )

        assert response.status_code == 204
        assert response.content == b""


def test_next_job_returns_expected_job(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()
    request_uid = _new_uid()
    job_uid = _new_uid()

    payload = {
        "invoice": {
            "invoice_number":
                "INV/2026/001",
        },
    }

    with TestClient(app) as client:
        client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
            ),
            json={
                "agent_uid": agent_uid,
                "version": "0.1.0",
                "environment": "test",
            },
        )

        with (
            app.state.database.session()
            as session
        ):
            agent_repository = (
                AgentRepository(
                    session
                )
            )

            certification_repository = (
                CertificationRepository(
                    session
                )
            )

            job_repository = (
                CentralJobRepository(
                    session
                )
            )

            agent = (
                agent_repository
                .get_by_uid(
                    agent_uid
                )
            )

            assert agent is not None

            certification, _ = (
                certification_repository
                .create_or_get(
                    request_uid=request_uid,
                    agent_uid=agent_uid,
                    invoice_number=(
                        "INV/2026/001"
                    ),
                    payload=payload,
                )
            )

            job_repository.create_or_get(
                job_uid=job_uid,
                certification_request=(
                    certification
                ),
                agent=agent,
                job_type="invoice.certify",
                payload=payload,
            )

            session.commit()

        response = client.get(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/jobs/next"
            )
        )

        assert response.status_code == 200

        assert response.json() == {
            "job_uid": job_uid,
            "job_type": "invoice.certify",
            "payload": payload,
        }


def test_report_completed_updates_central_state(
    tmp_path,
) -> None:
    app = _create_test_app(
        tmp_path
    )

    agent_uid = _new_uid()
    request_uid = _new_uid()
    job_uid = _new_uid()

    payload = {
        "invoice": {
            "invoice_number":
                "INV/2026/002",
        },
    }

    with TestClient(app) as client:
        client.put(
            (
                f"/api/v1/agents/"
                f"{agent_uid}/heartbeat"
            ),
            json={
                "agent_uid": agent_uid,
                "version": "0.1.0",
                "environment": "test",
            },
        )

        with (
            app.state.database.session()
            as session
        ):
            agent_repository = (
                AgentRepository(
                    session
                )
            )

            certification_repository = (
                CertificationRepository(
                    session
                )
            )

            job_repository = (
                CentralJobRepository(
                    session
                )
            )

            agent = (
                agent_repository
                .get_by_uid(
                    agent_uid
                )
            )

            assert agent is not None

            certification, _ = (
                certification_repository
                .create_or_get(
                    request_uid=request_uid,
                    agent_uid=agent_uid,
                    invoice_number=(
                        "INV/2026/002"
                    ),
                    payload=payload,
                )
            )

            job_repository.create_or_get(
                job_uid=job_uid,
                certification_request=(
                    certification
                ),
                agent=agent,
                job_type="invoice.certify",
                payload=payload,
            )

            session.commit()

        result = {
            "invoice_number":
                "INV/2026/002",
            "mid": "DT02200630-1",
            "ifu": "00225673B",
            "signature": "TEST001",
            "datetime": "20260918150000",
            "invoice_counter": 10,
            "total_counter": 20,
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
                f"{agent_uid}/jobs/"
                f"{job_uid}/status"
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
            "agent_uid": agent_uid,
            "job_uid": job_uid,
        }

        with (
            app.state.database.session()
            as session
        ):
            job = CentralJobRepository(
                session
            ).get_by_uid(
                job_uid
            )

            certification = (
                CertificationRepository(
                    session
                ).get_by_request_uid(
                    request_uid
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