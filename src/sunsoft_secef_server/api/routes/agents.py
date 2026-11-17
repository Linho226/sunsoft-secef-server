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
from sunsoft_secef_server.storage.auth_repositories import (
    OdooCredentialRepository,
)

from sunsoft_secef_server.storage.models import (
    Agent,
    AgentCredential,
    JobStatus,
    utc_now,
)
from sunsoft_secef_server.storage.repositories import (
    AgentMCFStatusRepository,
    CentralJobConflictError,
    CentralJobNotFoundError,
    CentralJobRepository,
    InvalidJobTransitionError,
)


ODOO_HEARTBEAT_STALE_SECONDS = 180


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

    if payload.mcf_status is not None:
        mcf_status = payload.mcf_status

        AgentMCFStatusRepository(
            session
        ).upsert(
            agent_id=agent.id,
            sent_transactions=(
                mcf_status.sent_transactions
            ),
            available_transactions=(
                mcf_status.available_transactions
            ),
            last_connection_datetime=(
                mcf_status.last_connection_datetime
            ),
            connection_age_seconds=(
                mcf_status.connection_age_seconds
            ),
            connection_stale=(
                mcf_status.connection_stale
            ),
            last_error=(
                mcf_status.last_error
            ),
        )

    session.flush()

    return AgentHeartbeatResponse(
        status="accepted",
        agent_uid=normalized_agent_uid,
    )


@router.get(
    "/{agent_uid}/odoo-status",
)
def get_agent_odoo_status(
    agent_uid: str,
    credential: AgentAuthDependency,
    session: SessionDependency,
) -> dict[str, object]:
    """
    Retourne l'etat Odoo du Tenant de l'Agent.

    Aucun appel direct vers Odoo n'est effectue.
    Le statut repose uniquement sur la presence
    centralisee du credential Odoo.
    """

    normalized_agent_uid = _normalize_identifier(
        agent_uid,
        "agent_uid",
    )

    agent = _require_authorized_agent(
        agent_uid=normalized_agent_uid,
        credential=credential,
        session=session,
    )

    if agent.tenant_id is None:
        return {
            "status": "not_linked",
            "credential_configured": False,
            "last_seen_at": None,
            "last_seen_age_seconds": None,
            "stale_after_seconds": (
                ODOO_HEARTBEAT_STALE_SECONDS
            ),
        }

    credentials = (
        OdooCredentialRepository(
            session
        ).list_active_for_tenant(
            agent.tenant_id
        )
    )

    if not credentials:
        return {
            "status": "not_linked",
            "credential_configured": False,
            "last_seen_at": None,
            "last_seen_age_seconds": None,
            "stale_after_seconds": (
                ODOO_HEARTBEAT_STALE_SECONDS
            ),
        }

    last_seen_values = [
        item.last_used_at
        for item in credentials
        if item.last_used_at is not None
    ]

    if not last_seen_values:
        return {
            "status": "unavailable",
            "credential_configured": True,
            "last_seen_at": None,
            "last_seen_age_seconds": None,
            "stale_after_seconds": (
                ODOO_HEARTBEAT_STALE_SECONDS
            ),
        }

    last_seen = max(
        last_seen_values
    )

    now = utc_now()

    comparable_last_seen = last_seen
    comparable_now = now

    if (
        comparable_last_seen.tzinfo is None
        and comparable_now.tzinfo is not None
    ):
        comparable_last_seen = (
            comparable_last_seen.replace(
                tzinfo=comparable_now.tzinfo
            )
        )

    elif (
        comparable_last_seen.tzinfo is not None
        and comparable_now.tzinfo is None
    ):
        comparable_now = (
            comparable_now.replace(
                tzinfo=comparable_last_seen.tzinfo
            )
        )

    age_seconds = int(
        max(
            0,
            (
                comparable_now
                - comparable_last_seen
            ).total_seconds(),
        )
    )

    odoo_status = (
        "linked"
        if age_seconds
        <= ODOO_HEARTBEAT_STALE_SECONDS
        else "unavailable"
    )

    return {
        "status": odoo_status,
        "credential_configured": True,
        "last_seen_at": (
            comparable_last_seen.isoformat()
        ),
        "last_seen_age_seconds": (
            age_seconds
        ),
        "stale_after_seconds": (
            ODOO_HEARTBEAT_STALE_SECONDS
        ),
    }


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


# Route publique de provisioning initial.
from sunsoft_secef_server.api.routes.activation import (
    router as activation_router,
)

router.include_router(
    activation_router
)
