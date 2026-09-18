import socket
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
import uvicorn
from fastapi import FastAPI

from sunsoft_secef_agent.central.client import (
    CentralServerClient,
)
from sunsoft_secef_agent.central.schemas import (
    AgentHeartbeatRequest,
    CentralJobReportRequest,
)
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


@pytest.fixture
def running_server(
    tmp_path,
) -> Iterator[tuple[FastAPI, str]]:
    """
    Lance réellement le serveur central sur localhost.

    Le test utilise une base SQLite temporaire et un port
    réseau libre attribué par le système.
    """

    database_path = (
        tmp_path
        / "agent-compatibility.db"
    )

    settings = Settings(
        _env_file=None,
        environment="test",
        host="127.0.0.1",
        database_url=(
            f"sqlite:///{database_path}"
        ),
        log_level="WARNING",
    )

    app = create_app(
        settings=settings
    )

    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    server_socket.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    server_socket.bind(
        ("127.0.0.1", 0)
    )

    server_socket.listen()

    port = server_socket.getsockname()[1]

    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )

    server = uvicorn.Server(
        config
    )

    thread = threading.Thread(
        target=server.run,
        kwargs={
            "sockets": [
                server_socket,
            ],
        },
        daemon=True,
    )

    thread.start()

    deadline = (
        time.monotonic()
        + 10.0
    )

    while not server.started:
        if not thread.is_alive():
            raise RuntimeError(
                "Le serveur central s'est arrêté "
                "pendant son démarrage."
            )

        if time.monotonic() >= deadline:
            server.should_exit = True
            thread.join(
                timeout=5.0
            )

            raise RuntimeError(
                "Le serveur central n'a pas démarré "
                "dans le délai prévu."
            )

        time.sleep(
            0.01
        )

    base_url = (
        f"http://127.0.0.1:{port}"
        "/api/v1/"
    )

    try:
        yield app, base_url

    finally:
        server.should_exit = True

        thread.join(
            timeout=10.0
        )

        if thread.is_alive():
            raise RuntimeError(
                "Le serveur central ne s'est pas "
                "arrêté correctement."
            )


def test_real_agent_client_talks_to_central_server(
    running_server,
) -> None:
    app, base_url = running_server

    agent_uid = str(
        uuid.uuid4()
    )

    request_uid = str(
        uuid.uuid4()
    )

    job_uid = str(
        uuid.uuid4()
    )

    invoice_number = (
        "INV/2026/AGENT-001"
    )

    job_payload = {
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
    }

    client = CentralServerClient(
        base_url=base_url,
        api_token=None,
        connect_timeout=2.0,
        read_timeout=5.0,
    )

    try:
        # -------------------------------------------------
        # 1. Health
        # -------------------------------------------------

        health = client.health()

        assert (
            health["status"]
            == "ok"
        )

        # -------------------------------------------------
        # 2. Heartbeat réel Agent -> serveur
        # -------------------------------------------------

        heartbeat = (
            client.send_heartbeat(
                AgentHeartbeatRequest(
                    agent_uid=agent_uid,
                    version="0.1.0",
                    environment="test",
                )
            )
        )

        assert (
            heartbeat.status
            == "accepted"
        )

        assert (
            heartbeat.agent_uid
            == agent_uid
        )

        # -------------------------------------------------
        # 3. Aucun Job initialement
        # -------------------------------------------------

        assert (
            client.fetch_next_job(
                agent_uid
            )
            is None
        )

        # -------------------------------------------------
        # 4. Création centrale d'une certification
        #    et de son Job.
        #
        # À terme cette opération sera provoquée
        # par Odoo via l'API centrale.
        # -------------------------------------------------

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

            certification, created = (
                certification_repository
                .create_or_get(
                    request_uid=request_uid,
                    agent_uid=agent_uid,
                    invoice_number=(
                        invoice_number
                    ),
                    payload=job_payload,
                )
            )

            assert created is True

            job, job_created = (
                job_repository
                .create_or_get(
                    job_uid=job_uid,
                    certification_request=(
                        certification
                    ),
                    agent=agent,
                    job_type=(
                        "invoice.certify"
                    ),
                    payload=job_payload,
                )
            )

            assert job_created is True

            assert (
                job.status
                == JobStatus.PENDING
            )

            session.commit()

        # -------------------------------------------------
        # 5. Le vrai client Agent récupère le Job
        # -------------------------------------------------

        central_job = (
            client.fetch_next_job(
                agent_uid
            )
        )

        assert (
            central_job
            is not None
        )

        assert (
            central_job.job_uid
            == job_uid
        )

        assert (
            central_job.job_type
            == "invoice.certify"
        )

        assert (
            central_job.payload
            == job_payload
        )

        # -------------------------------------------------
        # 6. Simulation du résultat de l'exécution locale
        #
        # Aucun MCF réel n'est utilisé dans ce test.
        # -------------------------------------------------

        result = {
            "invoice_number":
                invoice_number,
            "mid": "DT02200630-1",
            "ifu": "00225673B",
            "signature":
                "AGENTCOMPAT001",
            "datetime":
                "20260918153000",
            "invoice_counter": 101,
            "total_counter": 201,
            "qr_data": (
                "BFSECEF01;"
                "DT02200630-1;"
                "AGENTCOMPAT001;"
                "00225673B;"
                "20260918153000"
            ),
        }

        report_response = (
            client.report_job(
                agent_uid=agent_uid,
                job_uid=job_uid,
                payload=(
                    CentralJobReportRequest(
                        status="completed",
                        attempt_count=1,
                        result=result,
                        error_message=None,
                    )
                ),
            )
        )

        assert (
            report_response.status
            == "accepted"
        )

        assert (
            report_response.agent_uid
            == agent_uid
        )

        assert (
            report_response.job_uid
            == job_uid
        )

        # -------------------------------------------------
        # 7. Vérification de la persistance centrale
        # -------------------------------------------------

        with (
            app.state.database.session()
            as session
        ):
            stored_job = (
                CentralJobRepository(
                    session
                ).get_by_uid(
                    job_uid
                )
            )

            stored_certification = (
                CertificationRepository(
                    session
                ).get_by_request_uid(
                    request_uid
                )
            )

            assert (
                stored_job
                is not None
            )

            assert (
                stored_certification
                is not None
            )

            assert (
                stored_job.status
                == JobStatus.COMPLETED
            )

            assert (
                stored_job.attempt_count
                == 1
            )

            assert (
                stored_job.result
                == result
            )

            assert (
                stored_certification.status
                == JobStatus.COMPLETED
            )

            assert (
                stored_certification.result
                == result
            )

            assert (
                stored_certification.completed_at
                is not None
            )

        # -------------------------------------------------
        # 8. Un Job terminal ne doit plus être distribué
        # -------------------------------------------------

        assert (
            client.fetch_next_job(
                agent_uid
            )
            is None
        )

    finally:
        client.close()