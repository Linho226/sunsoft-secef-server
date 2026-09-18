import uuid

import pytest

from sunsoft_secef_server.storage.database import Database
from sunsoft_secef_server.storage.models import (
    JobStatus,
)
from sunsoft_secef_server.storage.repositories import (
    AgentRepository,
    CentralJobConflictError,
    CentralJobNotFoundError,
    CentralJobRepository,
    CertificationRepository,
    CertificationRequestConflictError,
    InvalidJobTransitionError,
)


def _new_uid() -> str:
    return str(uuid.uuid4())


def _create_stack(
    session,
):
    agent_uid = _new_uid()
    request_uid = _new_uid()
    job_uid = _new_uid()

    agent_repository = AgentRepository(
        session
    )

    certification_repository = (
        CertificationRepository(
            session
        )
    )

    job_repository = CentralJobRepository(
        session
    )

    agent = (
        agent_repository
        .register_or_update_heartbeat(
            agent_uid=agent_uid,
            version="0.1.0",
            environment="test",
        )
    )

    payload = {
        "invoice": {
            "invoice_number": "INV/2026/001",
        },
    }

    certification, _ = (
        certification_repository
        .create_or_get(
            request_uid=request_uid,
            agent_uid=agent_uid,
            invoice_number="INV/2026/001",
            payload=payload,
        )
    )

    job, _ = (
        job_repository
        .create_or_get(
            job_uid=job_uid,
            certification_request=certification,
            agent=agent,
            job_type="invoice.certify",
            payload=payload,
        )
    )

    return (
        agent,
        certification,
        job,
        agent_repository,
        certification_repository,
        job_repository,
    )


def test_agent_heartbeat_is_idempotent(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            repository = AgentRepository(
                session
            )

            agent_uid = _new_uid()

            first = (
                repository
                .register_or_update_heartbeat(
                    agent_uid=agent_uid,
                    version="0.1.0",
                    environment="test",
                )
            )

            first_id = first.id

            second = (
                repository
                .register_or_update_heartbeat(
                    agent_uid=agent_uid,
                    version="0.2.0",
                    environment="production",
                )
            )

            assert second.id == first_id
            assert second.version == "0.2.0"
            assert (
                second.environment
                == "production"
            )

    finally:
        database.dispose()


def test_certification_request_is_idempotent(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            repository = CertificationRepository(
                session
            )

            request_uid = _new_uid()
            agent_uid = _new_uid()

            payload = {
                "invoice_number":
                    "INV/2026/001",
            }

            first, first_created = (
                repository.create_or_get(
                    request_uid=request_uid,
                    agent_uid=agent_uid,
                    invoice_number=(
                        "INV/2026/001"
                    ),
                    payload=payload,
                )
            )

            second, second_created = (
                repository.create_or_get(
                    request_uid=request_uid,
                    agent_uid=agent_uid,
                    invoice_number=(
                        "INV/2026/001"
                    ),
                    payload=payload,
                )
            )

            assert first_created is True
            assert second_created is False
            assert second.id == first.id

    finally:
        database.dispose()


def test_certification_request_conflict(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            repository = CertificationRepository(
                session
            )

            request_uid = _new_uid()
            agent_uid = _new_uid()

            repository.create_or_get(
                request_uid=request_uid,
                agent_uid=agent_uid,
                invoice_number="INV/001",
                payload={"amount": 100},
            )

            with pytest.raises(
                CertificationRequestConflictError
            ):
                repository.create_or_get(
                    request_uid=request_uid,
                    agent_uid=agent_uid,
                    invoice_number="INV/001",
                    payload={"amount": 200},
                )

    finally:
        database.dispose()


def test_central_job_is_idempotent(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            (
                agent,
                certification,
                job,
                _,
                _,
                repository,
            ) = _create_stack(
                session
            )

            same_job, created = (
                repository.create_or_get(
                    job_uid=job.job_uid,
                    certification_request=(
                        certification
                    ),
                    agent=agent,
                    job_type="invoice.certify",
                    payload=job.payload,
                )
            )

            assert created is False
            assert same_job.id == job.id

    finally:
        database.dispose()


def test_next_job_can_be_redelivered(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            (
                agent,
                _,
                job,
                _,
                _,
                repository,
            ) = _create_stack(
                session
            )

            first = repository.get_next_for_agent(
                agent.agent_uid
            )

            second = repository.get_next_for_agent(
                agent.agent_uid
            )

            assert first is not None
            assert second is not None
            assert first.id == job.id
            assert second.id == job.id
            assert first.delivered_at is not None

    finally:
        database.dispose()


def test_processing_report_updates_job_and_request(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            (
                agent,
                certification,
                job,
                _,
                _,
                repository,
            ) = _create_stack(
                session
            )

            repository.report_status(
                agent_uid=agent.agent_uid,
                job_uid=job.job_uid,
                status=JobStatus.PROCESSING,
                attempt_count=1,
            )

            assert (
                job.status
                == JobStatus.PROCESSING
            )
            assert job.attempt_count == 1

            assert (
                certification.status
                == JobStatus.PROCESSING
            )

    finally:
        database.dispose()


def test_completed_report_updates_certification(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            (
                agent,
                certification,
                job,
                _,
                _,
                repository,
            ) = _create_stack(
                session
            )

            result = {
                "mid": "DT02200630-1",
                "signature": "TEST",
            }

            repository.report_status(
                agent_uid=agent.agent_uid,
                job_uid=job.job_uid,
                status=JobStatus.COMPLETED,
                attempt_count=1,
                result=result,
            )

            assert (
                job.status
                == JobStatus.COMPLETED
            )

            assert job.result == result
            assert job.completed_at is not None

            assert (
                certification.status
                == JobStatus.COMPLETED
            )

            assert (
                certification.result
                == result
            )

            assert (
                certification.completed_at
                is not None
            )

    finally:
        database.dispose()


def test_terminal_report_is_idempotent(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            (
                agent,
                _,
                job,
                _,
                _,
                repository,
            ) = _create_stack(
                session
            )

            result = {
                "mid": "DT02200630-1",
            }

            repository.report_status(
                agent_uid=agent.agent_uid,
                job_uid=job.job_uid,
                status=JobStatus.COMPLETED,
                attempt_count=1,
                result=result,
            )

            repository.report_status(
                agent_uid=agent.agent_uid,
                job_uid=job.job_uid,
                status=JobStatus.COMPLETED,
                attempt_count=1,
                result=result,
            )

            assert (
                job.status
                == JobStatus.COMPLETED
            )

            with pytest.raises(
                InvalidJobTransitionError
            ):
                repository.report_status(
                    agent_uid=agent.agent_uid,
                    job_uid=job.job_uid,
                    status=JobStatus.PROCESSING,
                    attempt_count=1,
                )

    finally:
        database.dispose()


def test_agent_cannot_report_another_agent_job(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite:///{tmp_path / 'test.db'}"
    )
    database.initialize()

    try:
        with database.session() as session:
            (
                _,
                _,
                job,
                _,
                _,
                repository,
            ) = _create_stack(
                session
            )

            with pytest.raises(
                CentralJobNotFoundError
            ):
                repository.report_status(
                    agent_uid=_new_uid(),
                    job_uid=job.job_uid,
                    status=(
                        JobStatus.PROCESSING
                    ),
                    attempt_count=1,
                )

    finally:
        database.dispose()