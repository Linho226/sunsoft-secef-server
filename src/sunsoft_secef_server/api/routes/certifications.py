import uuid

from fastapi import (
    APIRouter,
    HTTPException,
    status,
)

from sunsoft_secef_server.api.dependencies import (
    SessionDependency,
)
from sunsoft_secef_server.schemas import (
    CertificationCreateRequest,
    CertificationResponse,
)
from sunsoft_secef_server.storage.repositories import (
    AgentRepository,
    CentralJobConflictError,
    CentralJobRepository,
    CertificationRepository,
    CertificationRequestConflictError,
)


router = APIRouter(
    prefix="/certifications",
    tags=["certifications"],
)


def _build_response(
    certification,
    job,
) -> CertificationResponse:
    """Construit la réponse publique d'une certification."""

    return CertificationResponse(
        request_uid=certification.request_uid,
        job_uid=job.job_uid,
        agent_uid=certification.agent_uid,
        invoice_number=(
            certification.invoice_number
        ),
        status=certification.status.value,
        result=certification.result,
        error_message=(
            certification.error_message
        ),
    )


@router.post(
    "",
    response_model=CertificationResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "Agent central introuvable."
            ),
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                "Conflit d'idempotence."
            ),
        },
    },
)
def create_certification(
    payload: CertificationCreateRequest,
    session: SessionDependency,
) -> CertificationResponse:
    """
    Crée une demande centrale de certification.

    Le request_uid constitue l'identifiant métier
    d'idempotence fourni par Odoo.

    Un rejeu strictement identique retourne la même
    certification et le même Job central.
    """

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

    agent = agent_repository.get_by_uid(
        payload.agent_uid
    )

    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "L'Agent demandé n'est pas "
                "enregistré sur la plateforme."
            ),
        )

    try:
        certification, created = (
            certification_repository
            .create_or_get(
                request_uid=payload.request_uid,
                agent_uid=payload.agent_uid,
                invoice_number=(
                    payload.invoice_number
                ),
                payload=payload.payload,
            )
        )

    except CertificationRequestConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    # -------------------------------------------------
    # Idempotence :
    #
    # si Odoo rejoue le même request_uid, nous devons
    # retourner le même Job et surtout ne jamais créer
    # une nouvelle opération fiscale.
    # -------------------------------------------------

    if not created:
        existing_job = (
            job_repository
            .get_for_certification(
                certification.id
            )
        )

        if existing_job is None:
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "La certification existe "
                    "sans Job central associé."
                ),
            )

        if (
            existing_job.job_type
            != payload.job_type
        ):
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "Le request_uid existe déjà "
                    "avec un job_type différent."
                ),
            )

        return _build_response(
            certification,
            existing_job,
        )

    # -------------------------------------------------
    # Nouvelle demande :
    # création d'un Job technique unique.
    # -------------------------------------------------

    job_uid = str(
        uuid.uuid4()
    )

    try:
        job, _ = job_repository.create_or_get(
            job_uid=job_uid,
            certification_request=certification,
            agent=agent,
            job_type=payload.job_type,
            payload=payload.payload,
        )

    except CentralJobConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return _build_response(
        certification,
        job,
    )


@router.get(
    "/{request_uid}",
    response_model=CertificationResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "Certification introuvable."
            ),
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                "Certification incohérente."
            ),
        },
    },
)
def get_certification(
    request_uid: str,
    session: SessionDependency,
) -> CertificationResponse:
    """Retourne l'état courant d'une certification."""

    normalized_request_uid = (
        request_uid.strip()
    )

    if not normalized_request_uid:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "request_uid ne peut pas "
                "être vide."
            ),
        )

    certification_repository = (
        CertificationRepository(
            session
        )
    )

    job_repository = CentralJobRepository(
        session
    )

    certification = (
        certification_repository
        .get_by_request_uid(
            normalized_request_uid
        )
    )

    if certification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Demande de certification "
                "introuvable."
            ),
        )

    job = (
        job_repository
        .get_for_certification(
            certification.id
        )
    )

    if job is None:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "La certification existe "
                "sans Job central associé."
            ),
        )

    return _build_response(
        certification,
        job,
    )