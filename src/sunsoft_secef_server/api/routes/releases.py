from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    HTTPException,
    status,
)
from pydantic import BaseModel

from sunsoft_secef_server.api.dependencies import (
    SessionDependency,
)
from sunsoft_secef_server.storage.release_repositories import (
    AgentReleaseRepository,
)


router = APIRouter(
    prefix="/agent/releases",
    tags=["agent-releases"],
)


def _as_utc(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


class AgentReleaseResponse(BaseModel):
    """
    Métadonnées publiques de la version Agent actuellement publiée.

    Aucun chemin de stockage interne ni identifiant technique
    de release n'est exposé au client.
    """

    version: str
    filename: str
    sha256: str
    file_size: int
    download_url: str
    release_notes: str | None
    published_at: datetime | None


@router.get(
    "/latest",
    response_model=AgentReleaseResponse,
)
def get_latest_agent_release(
    session: SessionDependency,
) -> AgentReleaseResponse:
    """
    Retourne la version Windows actuellement publiée.
    """

    release = AgentReleaseRepository(
        session
    ).get_current()

    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Aucune version Agent "
                "n'est actuellement publiee."
            ),
        )

    return AgentReleaseResponse(
        version=release.version,
        filename=release.filename,
        sha256=release.sha256,
        file_size=release.file_size,
        download_url="/download/agent",
        release_notes=release.release_notes,
        published_at=_as_utc(
            release.published_at
        ),
    )
