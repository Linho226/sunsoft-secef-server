from fastapi import (
    APIRouter,
    HTTPException,
    Response,
    status,
)
from sqlalchemy.orm import Session

from sunsoft_secef_server.api.auth import (
    AgentAuthDependency,
)
from sunsoft_secef_server.api.dependencies import (
    SessionDependency,
)
from sunsoft_secef_server.schemas import (
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    CentralJob,
    CentralJobReportRequest,
    CentralJobReportResponse,
)
from sunsoft_secef_server.storage.models import (
    Agent,
    AgentCredential,
    JobStatus,
    utc_now,
)
from sunsoft_secef_server.storage.repositories import (
    CentralJobConflictError,
    CentralJobNotFoundError,
    CentralJobRepository,
    InvalidJobTransitionError,
)


router = APIRouter(
    prefix="/agents",
    tags=["agents"],
)


def _normalize_identifier(
    value: str,
    field_name: str,
) -> str:
    """Normalise un identifiant reçu dans l'URL."""

    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} invalide.",
        )

    normalized = value.strip()

    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{field_name} ne peut pas être vide."
            ),
        )

    return normalized


def _require_authorized_agent(
    *,
    agent_uid: str,
    credential: AgentCredential,
    session: Session,
) -> Agent:
    """
    Vérifie que le credential appartient exactement
    à l'Agent demandé dans l'URL.

    Un token Agent ne donne jamais accès aux routes
    d'un autre Agent, même du même Tenant.
    """

    agent = session.get(
        Agent,
        credential.agent_id,
    )

    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credential Agent invalide.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    if agent.agent_uid != agent_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Le credential Agent n'est pas "
                "autorisé pour cette ressource."
            ),
        )

    return agent


@router.put(
    "/{agent_uid}/heartbeat",
    response_model=AgentHeartbeatResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Authentification requise.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": (
                "Credential non autorisé pour cet Agent."
            ),
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                "agent_uid du chemin et du payload "
                "incompatibles."
            ),
        },
    },
)
def heartbeat(
    agent_uid: str,
    payload: AgentHeartbeatRequest,
    credential: AgentAuthDependency,
    session: SessionDependency,
) -> AgentHeartbeatResponse:
    """
    Met à jour un Agent central déjà provisionné.

    Le heartbeat ne crée plus d'Agent.
    L'Agent doit avoir été provisionné avec un Tenant
    et un credential avant son premier heartbeat.
    """

    normalized_agent_uid = _normalize_identifier(
        agent_uid,
        "agent_uid",
    )

    if (
        normalized_agent_uid
        != payload.agent_uid
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "agent_uid du chemin et du payload "
                "incompatibles."
            ),
        )

    agent = _require_authorized_agent(
        agent_uid=normalized_agent_uid,
        credential=credential,
        session=session,
    )

    agent.version = payload.version
    agent.environment = payload.environment
    agent.last_seen_at = utc_now()

    session.flush()

    return AgentHeartbeatResponse(
        status="accepted",
        agent_uid=normalized_agent_uid,
    )


@router.get(
    "/{agent_uid}/jobs/next",
    response_model=CentralJob,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Aucun Job disponible.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Authentification requise.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": (
                "Credential non autorisé pour cet Agent."
            ),
        },
    },
)
def get_next_job(
    agent_uid: str,
    credential: AgentAuthDependency,
    session: SessionDependency,
) -> CentralJob | Response:
    """Retourne le prochain Job de l'Agent."""

    normalized_agent_uid = _normalize_identifier(
        agent_uid,
        "agent_uid",
    )

    _require_authorized_agent(
        agent_uid=normalized_agent_uid,
        credential=credential,
        session=session,
    )

    job_repository = CentralJobRepository(
        session
    )

    job = job_repository.get_next_for_agent(
        normalized_agent_uid
    )

    if job is None:
        return Response(
            status_code=status.HTTP_204_NO_CONTENT,
        )

    return CentralJob(
        job_uid=job.job_uid,
        job_type=job.job_type,
        payload=job.payload,
    )


@router.put(
    "/{agent_uid}/jobs/{job_uid}/status",
    response_model=CentralJobReportResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Authentification requise.",
        },
        status.HTTP_403_FORBIDDEN: {
            "description": (
                "Credential non autorisé pour cet Agent."
            ),
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Job central introuvable.",
        },
        status.HTTP_409_CONFLICT: {
            "description": (
                "Transition d'état ou rapport "
                "terminal incompatible."
            ),
        },
    },
)
def report_job_status(
    agent_uid: str,
    job_uid: str,
    payload: CentralJobReportRequest,
    credential: AgentAuthDependency,
    session: SessionDependency,
) -> CentralJobReportResponse:
    """
    Enregistre l'état d'un Job remonté par l'Agent.

    Le credential doit appartenir exactement à l'Agent
    indiqué dans le chemin.

    Les états terminaux restent immuables. Un rapport
    terminal strictement identique peut être rejoué
    pour supporter la perte d'un ACK HTTP.
    """

    normalized_agent_uid = _normalize_identifier(
        agent_uid,
        "agent_uid",
    )

    normalized_job_uid = _normalize_identifier(
        job_uid,
        "job_uid",
    )

    _require_authorized_agent(
        agent_uid=normalized_agent_uid,
        credential=credential,
        session=session,
    )

    repository = CentralJobRepository(
        session
    )

    try:
        repository.report_status(
            agent_uid=normalized_agent_uid,
            job_uid=normalized_job_uid,
            status=JobStatus(
                payload.status
            ),
            attempt_count=payload.attempt_count,
            result=payload.result,
            error_message=payload.error_message,
        )

    except CentralJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job central introuvable.",
        ) from exc

    except (
        InvalidJobTransitionError,
        CentralJobConflictError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return CentralJobReportResponse(
        status="accepted",
        agent_uid=normalized_agent_uid,
        job_uid=normalized_job_uid,
    )