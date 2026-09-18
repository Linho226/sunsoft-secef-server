from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy.orm import Session

from sunsoft_secef_server.api.dependencies import (
    get_session,
)
from sunsoft_secef_server.schemas import (
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    CentralJob,
    CentralJobReportRequest,
    CentralJobReportResponse,
)
from sunsoft_secef_server.storage.models import (
    JobStatus,
)
from sunsoft_secef_server.storage.repositories import (
    AgentRepository,
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
    normalized_value = value.strip()

    if not normalized_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{field_name} ne peut pas être vide."
            ),
        )

    return normalized_value


@router.put(
    "/{agent_uid}/heartbeat",
    response_model=AgentHeartbeatResponse,
)
def heartbeat(
    agent_uid: str,
    payload: AgentHeartbeatRequest,
    session: Session = Depends(get_session),
) -> AgentHeartbeatResponse:
    """Enregistre ou actualise le heartbeat d'un Agent."""

    normalized_agent_uid = _normalize_identifier(
        agent_uid,
        "agent_uid",
    )

    if normalized_agent_uid != payload.agent_uid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "L'agent_uid de l'URL ne correspond "
                "pas à celui du heartbeat."
            ),
        )

    repository = AgentRepository(
        session
    )

    agent = (
        repository
        .register_or_update_heartbeat(
            agent_uid=payload.agent_uid,
            version=payload.version,
            environment=payload.environment,
        )
    )

    return AgentHeartbeatResponse(
        status="accepted",
        agent_uid=agent.agent_uid,
    )


@router.get(
    "/{agent_uid}/jobs/next",
    response_model=CentralJob,
    responses={
        status.HTTP_204_NO_CONTENT: {
            "description": "Aucun Job disponible.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Agent inconnu.",
        },
    },
)
def next_job(
    agent_uid: str,
    session: Session = Depends(get_session),
) -> CentralJob | Response:
    """Retourne le prochain Job destiné à l'Agent."""

    normalized_agent_uid = _normalize_identifier(
        agent_uid,
        "agent_uid",
    )

    agent_repository = AgentRepository(
        session
    )

    agent = agent_repository.get_by_uid(
        normalized_agent_uid
    )

    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent central introuvable.",
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
)
def report_job_status(
    agent_uid: str,
    job_uid: str,
    payload: CentralJobReportRequest,
    session: Session = Depends(get_session),
) -> CentralJobReportResponse:
    """Enregistre l'état d'un Job remonté par l'Agent."""

    normalized_agent_uid = _normalize_identifier(
        agent_uid,
        "agent_uid",
    )

    normalized_job_uid = _normalize_identifier(
        job_uid,
        "job_uid",
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

    except InvalidJobTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return CentralJobReportResponse(
        status="accepted",
        agent_uid=normalized_agent_uid,
        job_uid=normalized_job_uid,
    )