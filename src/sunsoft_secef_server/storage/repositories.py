from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from sunsoft_secef_server.storage.models import (
    Agent,
    CentralJob,
    CertificationRequest,
    JobStatus,
    utc_now,
)


class CentralRepositoryError(RuntimeError):
    """Erreur générique de la couche de persistance centrale."""


class AgentNotFoundError(CentralRepositoryError):
    """Agent central introuvable."""


class CertificationRequestNotFoundError(
    CentralRepositoryError
):
    """Demande de certification introuvable."""


class CertificationRequestConflictError(
    CentralRepositoryError
):
    """Conflit d'idempotence sur une certification."""


class CentralJobNotFoundError(CentralRepositoryError):
    """Job central introuvable."""


class CentralJobConflictError(CentralRepositoryError):
    """Conflit d'idempotence sur un Job central."""


class InvalidJobTransitionError(
    CentralRepositoryError
):
    """Transition d'état interdite pour un Job."""


def _normalize_required_text(
    value: str,
    field_name: str,
) -> str:
    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(
            f"{field_name} ne peut pas être vide."
        )

    return normalized_value


class AgentRepository:
    """Persistance des Agents Windows SECeF."""

    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_uid(
        self,
        agent_uid: str,
    ) -> Agent | None:
        normalized_uid = _normalize_required_text(
            agent_uid,
            "agent_uid",
        )

        statement = select(Agent).where(
            Agent.agent_uid == normalized_uid
        )

        return self.session.scalar(
            statement
        )

    def register_or_update_heartbeat(
        self,
        *,
        agent_uid: str,
        version: str,
        environment: str,
    ) -> Agent:
        normalized_uid = _normalize_required_text(
            agent_uid,
            "agent_uid",
        )

        normalized_version = _normalize_required_text(
            version,
            "version",
        )

        normalized_environment = (
            _normalize_required_text(
                environment,
                "environment",
            )
        )

        if normalized_environment not in {
            "development",
            "test",
            "production",
        }:
            raise ValueError(
                "Environnement Agent invalide."
            )

        agent = self.get_by_uid(
            normalized_uid
        )

        now = utc_now()

        if agent is None:
            agent = Agent(
                agent_uid=normalized_uid,
                version=normalized_version,
                environment=normalized_environment,
                last_seen_at=now,
            )

            self.session.add(agent)

        else:
            agent.version = normalized_version
            agent.environment = (
                normalized_environment
            )
            agent.last_seen_at = now

        self.session.flush()

        return agent


class CertificationRepository:
    """Persistance des demandes de certification Odoo."""

    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_request_uid(
        self,
        request_uid: str,
    ) -> CertificationRequest | None:
        normalized_uid = _normalize_required_text(
            request_uid,
            "request_uid",
        )

        statement = (
            select(CertificationRequest)
            .where(
                CertificationRequest.request_uid
                == normalized_uid
            )
        )

        return self.session.scalar(
            statement
        )

    def create_or_get(
        self,
        *,
        request_uid: str,
        agent_uid: str,
        invoice_number: str,
        payload: dict,
    ) -> tuple[
        CertificationRequest,
        bool,
    ]:
        normalized_request_uid = (
            _normalize_required_text(
                request_uid,
                "request_uid",
            )
        )

        normalized_agent_uid = (
            _normalize_required_text(
                agent_uid,
                "agent_uid",
            )
        )

        normalized_invoice_number = (
            _normalize_required_text(
                invoice_number,
                "invoice_number",
            )
        )

        if not isinstance(payload, dict):
            raise TypeError(
                "payload doit être un dictionnaire."
            )

        existing = self.get_by_request_uid(
            normalized_request_uid
        )

        if existing is not None:
            if (
                existing.agent_uid
                != normalized_agent_uid
                or existing.invoice_number
                != normalized_invoice_number
                or existing.payload
                != payload
            ):
                raise CertificationRequestConflictError(
                    "Le request_uid existe déjà "
                    "avec des données différentes."
                )

            return existing, False

        certification = CertificationRequest(
            request_uid=normalized_request_uid,
            agent_uid=normalized_agent_uid,
            invoice_number=(
                normalized_invoice_number
            ),
            status=JobStatus.PENDING,
            payload=deepcopy(payload),
        )

        self.session.add(
            certification
        )

        self.session.flush()

        return certification, True

    def sync_from_job(
        self,
        job: CentralJob,
    ) -> CertificationRequest:
        certification = (
            job.certification_request
        )

        certification.status = job.status
        certification.result = (
            deepcopy(job.result)
            if job.result is not None
            else None
        )
        certification.error_message = (
            job.error_message
        )

        if job.status in {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.UNKNOWN,
        }:
            certification.completed_at = (
                job.completed_at
                or utc_now()
            )
        else:
            certification.completed_at = None

        self.session.flush()

        return certification


class CentralJobRepository:
    """Persistance et cycle de vie des Jobs centraux."""

    _ALLOWED_TRANSITIONS = {
        JobStatus.PENDING: {
            JobStatus.PENDING,
            JobStatus.PROCESSING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.UNKNOWN,
        },
        JobStatus.PROCESSING: {
            JobStatus.PROCESSING,
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.UNKNOWN,
        },
        JobStatus.COMPLETED: {
            JobStatus.COMPLETED,
        },
        JobStatus.FAILED: {
            JobStatus.FAILED,
        },
        JobStatus.UNKNOWN: {
            JobStatus.UNKNOWN,
        },
    }

    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_uid(
        self,
        job_uid: str,
    ) -> CentralJob | None:
        normalized_uid = _normalize_required_text(
            job_uid,
            "job_uid",
        )

        statement = select(CentralJob).where(
            CentralJob.job_uid == normalized_uid
        )

        return self.session.scalar(
            statement
        )

    def create_or_get(
        self,
        *,
        job_uid: str,
        certification_request: CertificationRequest,
        agent: Agent,
        job_type: str,
        payload: dict,
    ) -> tuple[
        CentralJob,
        bool,
    ]:
        normalized_job_uid = (
            _normalize_required_text(
                job_uid,
                "job_uid",
            )
        )

        normalized_job_type = (
            _normalize_required_text(
                job_type,
                "job_type",
            )
        )

        if not isinstance(payload, dict):
            raise TypeError(
                "payload doit être un dictionnaire."
            )

        if (
            certification_request.agent_uid
            != agent.agent_uid
        ):
            raise CentralJobConflictError(
                "La certification et l'Agent "
                "ne correspondent pas."
            )

        existing = self.get_by_uid(
            normalized_job_uid
        )

        if existing is not None:
            if (
                existing.certification_request_id
                != certification_request.id
                or existing.agent_id
                != agent.id
                or existing.job_type
                != normalized_job_type
                or existing.payload
                != payload
            ):
                raise CentralJobConflictError(
                    "Le job_uid existe déjà "
                    "avec des données différentes."
                )

            return existing, False

        job = CentralJob(
            job_uid=normalized_job_uid,
            certification_request=(
                certification_request
            ),
            agent=agent,
            job_type=normalized_job_type,
            status=JobStatus.PENDING,
            attempt_count=0,
            payload=deepcopy(payload),
        )

        self.session.add(job)
        self.session.flush()

        return job, True

    def get_next_for_agent(
        self,
        agent_uid: str,
    ) -> CentralJob | None:
        normalized_agent_uid = (
            _normalize_required_text(
                agent_uid,
                "agent_uid",
            )
        )

        statement = (
            select(CentralJob)
            .join(Agent)
            .where(
                Agent.agent_uid
                == normalized_agent_uid,
                CentralJob.status.in_([
                    JobStatus.PENDING,
                    JobStatus.PROCESSING,
                ]),
            )
            .order_by(
                CentralJob.created_at.asc(),
                CentralJob.id.asc(),
            )
            .limit(1)
        )

        job = self.session.scalar(
            statement
        )

        if job is None:
            return None

        if job.delivered_at is None:
            job.delivered_at = utc_now()
            self.session.flush()

        return job

    def report_status(
        self,
        *,
        agent_uid: str,
        job_uid: str,
        status: JobStatus,
        attempt_count: int,
        result: dict | None = None,
        error_message: str | None = None,
    ) -> CentralJob:
        normalized_agent_uid = (
            _normalize_required_text(
                agent_uid,
                "agent_uid",
            )
        )

        normalized_job_uid = (
            _normalize_required_text(
                job_uid,
                "job_uid",
            )
        )

        if not isinstance(status, JobStatus):
            raise TypeError(
                "status doit être un JobStatus."
            )

        if attempt_count < 0:
            raise ValueError(
                "attempt_count ne peut pas être négatif."
            )

        if (
            result is not None
            and not isinstance(result, dict)
        ):
            raise TypeError(
                "result doit être un dictionnaire "
                "ou None."
            )

        statement = (
            select(CentralJob)
            .join(Agent)
            .where(
                CentralJob.job_uid
                == normalized_job_uid,
                Agent.agent_uid
                == normalized_agent_uid,
            )
        )

        job = self.session.scalar(
            statement
        )

        if job is None:
            raise CentralJobNotFoundError(
                "Job central introuvable "
                "pour cet Agent."
            )

        allowed = self._ALLOWED_TRANSITIONS[
            job.status
        ]

        if status not in allowed:
            raise InvalidJobTransitionError(
                f"Transition interdite : "
                f"{job.status.value} -> "
                f"{status.value}."
            )

        if attempt_count < job.attempt_count:
            raise InvalidJobTransitionError(
                "attempt_count ne peut pas diminuer."
            )

        if (
            job.status
            in {
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.UNKNOWN,
            }
            and status == job.status
        ):
            if (
                job.result is not None
                and result is not None
                and job.result != result
            ):
                raise CentralJobConflictError(
                    "Un rapport terminal différent "
                    "a déjà été enregistré."
                )

            if (
                job.error_message
                and error_message
                and job.error_message
                != error_message
            ):
                raise CentralJobConflictError(
                    "Un message terminal différent "
                    "a déjà été enregistré."
                )

        job.status = status
        job.attempt_count = attempt_count
        job.result = (
            deepcopy(result)
            if result is not None
            else None
        )

        normalized_error = (
            error_message.strip()
            if error_message
            else None
        )

        job.error_message = (
            normalized_error or None
        )

        if status in {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.UNKNOWN,
        }:
            if job.completed_at is None:
                job.completed_at = utc_now()
        else:
            job.completed_at = None

        certification = (
            job.certification_request
        )

        certification.status = job.status
        certification.result = (
            deepcopy(job.result)
            if job.result is not None
            else None
        )
        certification.error_message = (
            job.error_message
        )
        certification.completed_at = (
            job.completed_at
        )

        self.session.flush()

        return job