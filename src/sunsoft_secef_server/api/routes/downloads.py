from html import escape
from pathlib import Path

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
)

from sunsoft_secef_server.api.dependencies import (
    SessionDependency,
)
from sunsoft_secef_server.storage.release_repositories import (
    AgentReleaseRepository,
)


router = APIRouter(
    tags=["downloads"],
    include_in_schema=False,
)


def _release_path(
    request: Request,
    storage_path: str,
) -> Path:

    settings = getattr(
        request.app.state,
        "settings",
        None,
    )

    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuration indisponible.",
        )

    root = Path(
        settings.agent_release_storage_dir
    ).expanduser().resolve()

    candidate = (
        root / storage_path
    ).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier introuvable.",
        )

    return candidate


def _format_size(
    value: int | None,
) -> str:

    if not value:
        return "-"

    if value >= 1024 ** 3:
        return (
            f"{value / (1024 ** 3):.2f} Go"
        )

    if value >= 1024 ** 2:
        return (
            f"{value / (1024 ** 2):.1f} Mo"
        )

    if value >= 1024:
        return (
            f"{value / 1024:.1f} Ko"
        )

    return f"{value} octets"


def _format_date(
    value,
) -> str:

    if value is None:
        return "-"

    try:
        return value.strftime(
            "%d/%m/%Y à %H:%M"
        )
    except Exception:
        return str(value)


def _public_html(
    release,
    file_available: bool,
) -> str:

    if release is None:

        version = "-"
        filename = "-"
        size = "-"
        published = "-"
        sha256 = "-"
        notes = (
            "Aucune version de l'Agent Windows "
            "n'est actuellement publiée."
        )

        status_html = (
            '<span class="badge badge-off">'
            'Indisponible'
            '</span>'
        )

        download_html = (
            '<div class="download disabled">'
            'Aucune version disponible'
            '</div>'
        )

    else:

        version = escape(
            str(release.version)
        )

        filename = escape(
            str(release.filename)
        )

        size = escape(
            _format_size(
                release.file_size
            )
        )

        published = escape(
            _format_date(
                release.published_at
            )
        )

        sha256 = escape(
            str(
                release.sha256
            ).upper()
        )

        raw_notes = (
            release.release_notes
            or "Version stable de Sunsoft SECeF Agent."
        )

        notes = escape(
            str(raw_notes)
        ).replace(
            "\n",
            "<br>"
        )

        if file_available:

            status_html = (
                '<span class="badge badge-on">'
                'Disponible'
                '</span>'
            )

            download_html = (
                '<a class="download" '
                'href="/download/agent">'
                '<span class="win">&#8862;</span>'
                '<span>'
                '<strong>Télécharger pour Windows</strong>'
                '<small>'
                + filename
                + '</small>'
                '</span>'
                '</a>'
            )

        else:

            status_html = (
                '<span class="badge badge-off">'
                'Fichier indisponible'
                '</span>'
            )

            download_html = (
                '<div class="download disabled">'
                'Téléchargement temporairement indisponible'
                '</div>'
            )


    page = (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "public"
        / "agent.html"
    ).read_text(encoding="utf-8")

    values = {
        "__STATUS__": status_html,
        "__VERSION__": version,
        "__DOWNLOAD__": download_html,
        "__SIZE__": size,
        "__PUBLISHED__": published,
        "__NOTES__": notes,
        "__SHA__": sha256,
        "__FILENAME__": filename,
    }

    for marker, value in values.items():
        page = page.replace(
            marker,
            value,
        )

    return page


@router.get(
    "/agent",
    name="agent-public-page",
    response_class=HTMLResponse,
)
def public_agent_page(
    request: Request,
    session: SessionDependency,
):

    release = AgentReleaseRepository(
        session
    ).get_current()

    available = False

    if release is not None:

        try:

            path = _release_path(
                request,
                release.storage_path,
            )

            available = path.is_file()

        except HTTPException:

            available = False

    return HTMLResponse(
        content=_public_html(
            release,
            available,
        ),
        status_code=status.HTTP_200_OK,
        headers={
            "Cache-Control":
                "no-store",
            "X-Content-Type-Options":
                "nosniff",
            "X-Frame-Options":
                "DENY",
            "Referrer-Policy":
                "strict-origin-when-cross-origin",
            "Content-Security-Policy": (
                "default-src 'none'; "
                "style-src 'self'; "
                "base-uri 'none'; "
                "form-action 'self'; "
                "frame-ancestors 'none'"
            ),
        },
    )


@router.get(
    "/download/agent",
    name="download-agent",
)
def download_current_agent(
    request: Request,
    session: SessionDependency,
):

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

    path = _release_path(
        request,
        release.storage_path,
    )

    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier Agent introuvable.",
        )

    return FileResponse(
        path=path,
        filename=release.filename,
        media_type="application/octet-stream",
        headers={
            "Cache-Control":
                "no-store",
            "X-Content-Type-Options":
                "nosniff",
            "X-Sunsoft-SECeF-Version":
                release.version,
            "X-Sunsoft-SECeF-SHA256":
                release.sha256,
        },
    )
