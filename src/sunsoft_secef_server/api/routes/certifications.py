import uuid

from fastapi import (
    APIRouter,
    HTTPException,
    status,
)

from sunsoft_secef_server.api.auth import (
    OdooAuthDependency,
)
from sunsoft_secef_server.api.dependencies import (
    SessionDependency,
)
from sunsoft_secef_server.schemas import (
    CertificationCreateRequest,
    CertificationResponse,
)
from sunsoft_secef_server.storage.models import (
    Agent,
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


def _require_agent_for_tenant(
    *,
    agent_uid: str,
    tenant_id: int,
    session,
) -> Agent:
    """
    Vérifie que l'Agent demandé existe et appartient
    au Tenant authentifié par le token Odoo.
    """

    agent = AgentRepository(
        session
    ).get_by_uid(
        agent_uid
    )

    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "L'Agent demandé n'est pas "
                "enregistré sur la plateforme."
            ),
        )

    if (
        agent.tenant_id is None
        or agent.tenant_id != tenant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Cet Agent n'est pas autorisé "
                "pour le Tenant authentifié."
            ),
        )

    return agent


def _require_certification_for_tenant(
    *,
    certification,
    job,
    tenant_id: int,
    session,
) -> Agent:
    """
    Vérifie qu'une certification appartient au Tenant.

    Une certification étrangère est exposée comme
    inexistante afin d'éviter l'énumération des
    request_uid entre Tenants.
    """

    agent = session.get(
        Agent,
        job.agent_id,
    )

    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "La certification référence "
                "un Agent central introuvable."
            ),
        )

    if (
        agent.agent_uid
        != certification.agent_uid
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "La certification et son Job "
                "référencent des Agents différents."
            ),
        )

    if (
        agent.tenant_id is None
        or agent.tenant_id != tenant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Demande de certification "
                "introuvable."
            ),
        )

    return agent


@router.post(
    "",
    response_model=CertificationResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "Authentification Odoo requise."
            ),
        },
        status.HTTP_403_FORBIDDEN: {
            "description": (
                "Agent non autorisé pour ce Tenant."
            ),
        },
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
    credential: OdooAuthDependency,
    session: SessionDependency,
) -> CertificationResponse:
    """
    Crée une demande centrale de certification.

    Le Bearer token Odoo détermine le Tenant autorisé.

    Le Tenant ne peut créer un Job que pour un Agent
    qui lui appartient.

    Le request_uid constitue l'identifiant métier
    d'idempotence fourni par Odoo.
    """

    agent = _require_agent_for_tenant(
        agent_uid=payload.agent_uid,
        tenant_id=credential.tenant_id,
        session=session,
    )

    certification_repository = (
        CertificationRepository(
            session
        )
    )

    job_repository = CentralJobRepository(
        session
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
    # Rejeu idempotent
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
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "La certification existe "
                    "sans Job central associé."
                ),
            )

        # Vérification supplémentaire :
        # même en cas de rejeu, le Job doit toujours
        # appartenir au Tenant authentifié.
        _require_certification_for_tenant(
            certification=certification,
            job=existing_job,
            tenant_id=credential.tenant_id,
            session=session,
        )

        if (
            existing_job.job_type
            != payload.job_type
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
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
    # Nouvelle demande
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
        status.HTTP_401_UNAUTHORIZED: {
            "description": (
                "Authentification Odoo requise."
            ),
        },
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
    credential: OdooAuthDependency,
    session: SessionDependency,
) -> CertificationResponse:
    """
    Retourne l'état courant d'une certification.

    Une instance Odoo ne peut consulter que les
    certifications appartenant à son propre Tenant.
    """

    normalized_request_uid = (
        request_uid.strip()
    )

    if not normalized_request_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "La certification existe "
                "sans Job central associé."
            ),
        )

    _require_certification_for_tenant(
        certification=certification,
        job=job,
        tenant_id=credential.tenant_id,
        session=session,
    )

    return _build_response(
        certification,
        job,
    )