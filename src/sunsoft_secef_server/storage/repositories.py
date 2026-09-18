from copy import deepcopy
from typing import Final

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sunsoft_secef_server.storage.models import (
    Agent,
    CentralJob,
    CertificationRequest,
    JobStatus,
    utc_now,
)


VALID_AGENT_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {
        "development",
        "test",
        "production",
    }
)

TERMINAL_JOB_STATUSES: Final[frozenset[JobStatus]] = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.UNKNOWN,
    }
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
    """Normalise une chaîne obligatoire."""

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} doit être une chaîne."
        )

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(
            f"{field_name} ne peut pas être vide."
        )

    return normalized_value


def _normalize_optional_text(
    value: str | None,
    field_name: str,
) -> str | None:
    """Normalise une chaîne facultative."""

    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} doit être une chaîne "
            "ou None."
        )

    normalized_value = value.strip()

    return normalized_value or None


def _validate_payload(
    payload: dict,
    field_name: str = "payload",
) -> dict:
    """Valide et copie un payload JSON."""

    if not isinstance(payload, dict):
        raise TypeError(
            f"{field_name} doit être un dictionnaire."
        )

    if not payload:
        raise ValueError(
            f"{field_name} ne peut pas être vide."
        )

    return deepcopy(payload)


def _validate_optional_result(
    result: dict | None,
) -> dict | None:
    """Valide et copie un résultat JSON facultatif."""

    if result is None:
        return None

    if not isinstance(result, dict):
        raise TypeError(
            "result doit être un dictionnaire "
            "ou None."
        )

    return deepcopy(result)


def _sync_certification_from_job(
    job: CentralJob,
) -> CertificationRequest:
    """Synchronise l'état métier avec l'état du Job."""

    certification = job.certification_request

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
        if job.status in TERMINAL_JOB_STATUSES
        else None
    )

    return certification


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
        """Recherche un Agent par son identifiant."""

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

    def require_by_uid(
        self,
        agent_uid: str,
    ) -> Agent:
        """Retourne l'Agent ou lève une erreur explicite."""

        agent = self.get_by_uid(
            agent_uid
        )

        if agent is None:
            raise AgentNotFoundError(
                "Agent central introuvable."
            )

        return agent

    def register_or_update_heartbeat(
        self,
        *,
        agent_uid: str,
        version: str,
        environment: str,
    ) -> Agent:
        """Crée ou actualise le heartbeat d'un Agent."""

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

        if (
            normalized_environment
            not in VALID_AGENT_ENVIRONMENTS
        ):
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

            self.session.add(
                agent
            )

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
        """Recherche une certification par request_uid."""

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

    def require_by_request_uid(
        self,
        request_uid: str,
    ) -> CertificationRequest:
        """Retourne la certification ou lève une erreur."""

        certification = self.get_by_request_uid(
            request_uid
        )

        if certification is None:
            raise CertificationRequestNotFoundError(
                "Demande de certification introuvable."
            )

        return certification

    @staticmethod
    def _ensure_same_request(
        existing: CertificationRequest,
        *,
        agent_uid: str,
        invoice_number: str,
        payload: dict,
    ) -> None:
        """Vérifie qu'un request_uid rejoué est identique."""

        if (
            existing.agent_uid != agent_uid
            or existing.invoice_number
            != invoice_number
            or existing.payload != payload
        ):
            raise CertificationRequestConflictError(
                "Le request_uid existe déjà "
                "avec des données différentes."
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
        """
        Crée une certification de manière idempotente.

        Retourne:
            (certification, True)
                si elle vient d'être créée.

            (certification, False)
                si une demande strictement identique
                existait déjà.
        """

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

        safe_payload = _validate_payload(
            payload
        )

        existing = self.get_by_request_uid(
            normalized_request_uid
        )

        if existing is not None:
            self._ensure_same_request(
                existing,
                agent_uid=normalized_agent_uid,
                invoice_number=(
                    normalized_invoice_number
                ),
                payload=safe_payload,
            )

            return existing, False

        certification = CertificationRequest(
            request_uid=normalized_request_uid,
            agent_uid=normalized_agent_uid,
            invoice_number=(
                normalized_invoice_number
            ),
            status=JobStatus.PENDING,
            payload=safe_payload,
        )

        try:
            with self.session.begin_nested():
                self.session.add(
                    certification
                )

                self.session.flush()

        except IntegrityError:
            existing = self.get_by_request_uid(
                normalized_request_uid
            )

            if existing is None:
                raise

            self._ensure_same_request(
                existing,
                agent_uid=normalized_agent_uid,
                invoice_number=(
                    normalized_invoice_number
                ),
                payload=safe_payload,
            )

            return existing, False

        return certification, True

    def sync_from_job(
        self,
        job: CentralJob,
    ) -> CertificationRequest:
        """Synchronise la certification depuis son Job."""

        certification = (
            _sync_certification_from_job(
                job
            )
        )

        self.session.flush()

        return certification


class CentralJobRepository:
    """Persistance et cycle de vie des Jobs centraux."""

    _ALLOWED_TRANSITIONS: Final = {
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
        """Recherche un Job par son identifiant."""

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

    def require_by_uid(
        self,
        job_uid: str,
    ) -> CentralJob:
        """Retourne un Job ou lève une erreur."""

        job = self.get_by_uid(
            job_uid
        )

        if job is None:
            raise CentralJobNotFoundError(
                "Job central introuvable."
            )

        return job

    def get_for_certification(
        self,
        certification_request_id: int,
    ) -> CentralJob | None:
        """
        Retourne le premier Job associé
        à une demande de certification.
        """

        if (
            not isinstance(
                certification_request_id,
                int,
            )
            or isinstance(
                certification_request_id,
                bool,
            )
            or certification_request_id <= 0
        ):
            raise ValueError(
                "certification_request_id "
                "doit être un entier positif."
            )

        statement = (
            select(CentralJob)
            .where(
                CentralJob.certification_request_id
                == certification_request_id
            )
            .order_by(
                CentralJob.created_at.asc(),
                CentralJob.id.asc(),
            )
            .limit(1)
        )

        return self.session.scalar(
            statement
        )

    @staticmethod
    def _ensure_same_job(
        existing: CentralJob,
        *,
        certification_request: CertificationRequest,
        agent: Agent,
        job_type: str,
        payload: dict,
    ) -> None:
        """Vérifie qu'un job_uid rejoué est identique."""

        if (
            existing.certification_request_id
            != certification_request.id
            or existing.agent_id != agent.id
            or existing.job_type != job_type
            or existing.payload != payload
        ):
            raise CentralJobConflictError(
                "Le job_uid existe déjà "
                "avec des données différentes."
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
        """Crée un Job central de manière idempotente."""

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

        safe_payload = _validate_payload(
            payload
        )

        if certification_request.id is None:
            raise ValueError(
                "La certification doit être persistée "
                "avant la création du Job."
            )

        if agent.id is None:
            raise ValueError(
                "L'Agent doit être persisté "
                "avant la création du Job."
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
            self._ensure_same_job(
                existing,
                certification_request=(
                    certification_request
                ),
                agent=agent,
                job_type=normalized_job_type,
                payload=safe_payload,
            )

            return existing, False

        # Important :
        # on utilise les clés étrangères directement.
        #
        # Cela évite d'attacher le CentralJob aux relations
        # Agent.jobs / CertificationRequest.jobs avant son
        # ajout effectif à la Session SQLAlchemy.
        job = CentralJob(
            job_uid=normalized_job_uid,
            certification_request_id=(
                certification_request.id
            ),
            agent_id=agent.id,
            job_type=normalized_job_type,
            status=JobStatus.PENDING,
            attempt_count=0,
            payload=safe_payload,
        )

        try:
            with self.session.begin_nested():
                self.session.add(
                    job
                )

                self.session.flush()

        except IntegrityError:
            existing = self.get_by_uid(
                normalized_job_uid
            )

            if existing is None:
                raise

            self._ensure_same_job(
                existing,
                certification_request=(
                    certification_request
                ),
                agent=agent,
                job_type=normalized_job_type,
                payload=safe_payload,
            )

            return existing, False

        return job, True

    def get_next_for_agent(
        self,
        agent_uid: str,
    ) -> CentralJob | None:
        """
        Retourne le prochain Job distribuable.

        Un Job pending ou processing peut être redélivré.
        Cette propriété est nécessaire pour la reprise
        après perte réseau ou redémarrage de l'Agent.
        """

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
                CentralJob.status.in_(
                    [
                        JobStatus.PENDING,
                        JobStatus.PROCESSING,
                    ]
                ),
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

    @staticmethod
    def _validate_terminal_replay(
        *,
        job: CentralJob,
        status: JobStatus,
        attempt_count: int,
        result: dict | None,
        error_message: str | None,
    ) -> None:
        """
        Vérifie qu'un rapport terminal répété
        est strictement identique au premier.

        Cela protège notamment contre un ACK perdu :
        l'Agent peut renvoyer le même rapport sans
        modifier le résultat fiscal déjà enregistré.
        """

        if job.status != status:
            raise InvalidJobTransitionError(
                f"Transition interdite : "
                f"{job.status.value} -> "
                f"{status.value}."
            )

        if job.attempt_count != attempt_count:
            raise CentralJobConflictError(
                "Le Job terminal a déjà été enregistré "
                "avec un attempt_count différent."
            )

        if job.result != result:
            raise CentralJobConflictError(
                "Le Job terminal a déjà été enregistré "
                "avec un résultat différent."
            )

        if job.error_message != error_message:
            raise CentralJobConflictError(
                "Le Job terminal a déjà été enregistré "
                "avec un message différent."
            )

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
        """
        Enregistre un état remonté par un Agent.

        Les états terminaux sont immuables.
        Une répétition strictement identique est
        acceptée afin de supporter la perte d'ACK.
        """

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

        if not isinstance(
            status,
            JobStatus,
        ):
            raise TypeError(
                "status doit être un JobStatus."
            )

        if (
            not isinstance(
                attempt_count,
                int,
            )
            or isinstance(
                attempt_count,
                bool,
            )
        ):
            raise TypeError(
                "attempt_count doit être un entier."
            )

        if attempt_count < 0:
            raise ValueError(
                "attempt_count ne peut pas être négatif."
            )

        safe_result = _validate_optional_result(
            result
        )

        normalized_error = (
            _normalize_optional_text(
                error_message,
                "error_message",
            )
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

        # Un état terminal est fiscalement immuable.
        #
        # Le même rapport est cependant accepté
        # lorsqu'il est strictement identique.
        #
        # Cela permet à l'Agent de répéter un PUT
        # lorsque l'ACK HTTP précédent a été perdu.
        if job.status in TERMINAL_JOB_STATUSES:
            self._validate_terminal_replay(
                job=job,
                status=status,
                attempt_count=attempt_count,
                result=safe_result,
                error_message=normalized_error,
            )

            return job

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

        job.status = status
        job.attempt_count = attempt_count
        job.result = safe_result
        job.error_message = normalized_error

        if status in TERMINAL_JOB_STATUSES:
            if job.completed_at is None:
                job.completed_at = utc_now()

        else:
            job.completed_at = None

        _sync_certification_from_job(
            job
        )

        self.session.flush()

        return job