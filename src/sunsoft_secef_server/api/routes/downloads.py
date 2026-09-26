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


    page = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>
<title>
Sunsoft SECeF Agent - Téléchargement officiel
</title>

<style>
:root {
    --navy: #0b2342;
    --blue: #1684e8;
    --text: #17263a;
    --muted: #69788b;
    --border: #e2e8f0;
    --bg: #f4f7fb;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;
    font-family:
        "Segoe UI",
        Arial,
        sans-serif;
    color: var(--text);
    background:
        radial-gradient(
            circle at 90% 0%,
            rgba(22,132,232,.12),
            transparent 30%
        ),
        var(--bg);
}

header {
    height: 72px;
    display: flex;
    align-items: center;
    background: rgba(255,255,255,.94);
    border-bottom: 1px solid var(--border);
}

.header-inner,
main {
    width: min(1140px, calc(100% - 40px));
    margin: 0 auto;
}

.header-inner {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.brand {
    display: flex;
    align-items: center;
    gap: 12px;
}

.logo {
    width: 43px;
    height: 43px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    background:
        linear-gradient(
            135deg,
            #178cf2,
            #176cc4
        );
    color: white;
    font-size: 21px;
    font-weight: 900;
}

.brand strong {
    display: block;
    color: var(--navy);
    font-size: 16px;
}

.brand small {
    display: block;
    margin-top: 3px;
    color: var(--muted);
}

.official {
    padding: 8px 12px;
    border-radius: 999px;
    background: #edf5fd;
    color: #175d9f;
    font-size: 11px;
    font-weight: 800;
}

main {
    padding: 58px 0 70px;
}

.hero {
    display: grid;
    grid-template-columns:
        minmax(0, 1.35fr)
        minmax(340px, .65fr);
    gap: 34px;
    align-items: center;
}

.eyebrow {
    color: #176db2;
    font-size: 12px;
    font-weight: 900;
    letter-spacing: .09em;
    text-transform: uppercase;
}

h1 {
    max-width: 690px;
    margin: 15px 0 0;
    color: var(--navy);
    font-size: clamp(40px, 5vw, 62px);
    line-height: 1.04;
    letter-spacing: -.04em;
}

.lead {
    max-width: 670px;
    margin: 22px 0 0;
    color: #5e6f82;
    font-size: 17px;
    line-height: 1.7;
}

.pills {
    display: flex;
    flex-wrap: wrap;
    gap: 9px;
    margin-top: 25px;
}

.pill {
    padding: 8px 11px;
    border: 1px solid #dde6ef;
    border-radius: 999px;
    background: rgba(255,255,255,.8);
    color: #52667d;
    font-size: 11px;
    font-weight: 700;
}

.card {
    padding: 27px;
    border: 1px solid rgba(20,60,100,.10);
    border-radius: 22px;
    background: white;
    box-shadow:
        0 20px 55px rgba(12,42,74,.10);
}

.card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
}

.windows {
    width: 58px;
    height: 58px;
    display: grid;
    place-items: center;
    border-radius: 15px;
    background: #eef6fe;
    color: #1476ce;
    font-size: 31px;
    font-weight: 900;
}

.badge {
    display: inline-flex;
    align-items: center;
    min-height: 29px;
    padding: 0 11px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 900;
}

.badge-on {
    color: #176b49;
    background: #e8f7ef;
}

.badge-off {
    color: #9b620e;
    background: #fff4e3;
}

.card h2 {
    margin: 21px 0 5px;
    color: var(--navy);
    font-size: 22px;
}

.version {
    margin-bottom: 20px;
    color: var(--muted);
    font-size: 13px;
}

.download {
    min-height: 64px;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 13px;
    padding: 10px 18px;
    border-radius: 13px;
    background:
        linear-gradient(
            135deg,
            #146fc5,
            #248eea
        );
    color: white;
    text-decoration: none;
    box-shadow:
        0 10px 24px rgba(36,142,234,.20);
}

.download strong,
.download small {
    display: block;
}

.download strong {
    font-size: 14px;
}

.download small {
    max-width: 245px;
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 10px;
    opacity: .82;
}

.download.disabled {
    background: #edf1f5;
    color: #7c8897;
    box-shadow: none;
    font-size: 12px;
    font-weight: 800;
    text-align: center;
}

.win {
    font-size: 25px;
}

.meta {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 11px;
    margin-top: 17px;
}

.meta-box {
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: #fafbfd;
}

.meta-box span {
    display: block;
    margin-bottom: 4px;
    color: var(--muted);
    font-size: 9px;
    font-weight: 900;
    text-transform: uppercase;
}

.meta-box strong {
    font-size: 11px;
}

.details {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
    margin-top: 34px;
}

.panel {
    padding: 25px;
    border: 1px solid var(--border);
    border-radius: 17px;
    background: rgba(255,255,255,.94);
}

.panel h3 {
    margin: 0 0 12px;
    color: var(--navy);
    font-size: 16px;
}

.panel p {
    margin: 0;
    color: #687789;
    font-size: 13px;
    line-height: 1.7;
}

.hash {
    display: block;
    margin-top: 13px;
    padding: 13px;
    border-radius: 9px;
    background: #f4f7fa;
    color: #42566d;
    font-family:
        Consolas,
        monospace;
    font-size: 10px;
    overflow-wrap: anywhere;
}

.info {
    display: grid;
    gap: 13px;
}

.info-row {
    display: flex;
    align-items: flex-start;
    gap: 11px;
}

.check {
    width: 23px;
    height: 23px;
    flex: 0 0 23px;
    display: grid;
    place-items: center;
    border-radius: 7px;
    background: #e8f6ef;
    color: #176c49;
    font-size: 11px;
    font-weight: 900;
}

.info-row strong {
    display: block;
    color: #2b3d52;
    font-size: 12px;
}

.info-row span {
    display: block;
    margin-top: 2px;
    color: #748296;
    font-size: 11px;
    overflow-wrap: anywhere;
}

footer {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #e2e8f0;
    color: #8490a0;
    text-align: center;
    font-size: 10px;
}

@media (max-width: 880px) {

    .hero,
    .details {
        grid-template-columns: 1fr;
    }
}

@media (max-width: 560px) {

    .header-inner,
    main {
        width: calc(100% - 26px);
    }

    main {
        padding-top: 34px;
    }

    .official {
        display: none;
    }

    .card,
    .panel {
        padding: 20px;
    }

    .meta {
        grid-template-columns: 1fr;
    }
}
</style>
</head>

<body>

<header>
    <div class="header-inner">

        <div class="brand">
            <div class="logo">S</div>

            <div>
                <strong>Sunsoft SECeF</strong>
                <small>
                    Sunsoft International SARL
                </small>
            </div>
        </div>

        <div class="official">
            Centre de téléchargement officiel
        </div>

    </div>
</header>


<main>

<section class="hero">

    <div>

        <div class="eyebrow">
            Agent Windows officiel
        </div>

        <h1>
            Sunsoft SECeF Agent
        </h1>

        <p class="lead">
            Téléchargez l'Agent Windows Sunsoft SECeF
            depuis la plateforme officielle.
            Aucun compte ni aucune connexion
            n'est nécessaire pour le téléchargement.
        </p>

        <div class="pills">
            <span class="pill">
                Version officielle
            </span>
            <span class="pill">
                Contrôle SHA-256
            </span>
            <span class="pill">
                Windows
            </span>
        </div>

    </div>


    <aside class="card">

        <div class="card-top">
            <div class="windows">&#8862;</div>
            __STATUS__
        </div>

        <h2>
            Agent pour Windows
        </h2>

        <div class="version">
            Version __VERSION__
        </div>

        __DOWNLOAD__

        <div class="meta">

            <div class="meta-box">
                <span>Taille</span>
                <strong>__SIZE__</strong>
            </div>

            <div class="meta-box">
                <span>Publication</span>
                <strong>__PUBLISHED__</strong>
            </div>

        </div>

    </aside>

</section>


<section class="details">

    <article class="panel">

        <h3>
            Notes de version
        </h3>

        <p>
            __NOTES__
        </p>

    </article>


    <article class="panel">

        <h3>
            Vérification d'intégrité
        </h3>

        <p>
            Empreinte SHA-256 officielle du fichier.
        </p>

        <code class="hash">
            __SHA__
        </code>

    </article>

</section>


<section class="details">

    <article class="panel">

        <h3>
            Informations du logiciel
        </h3>

        <div class="info">

            <div class="info-row">
                <div class="check">&#10003;</div>
                <div>
                    <strong>Éditeur</strong>
                    <span>
                        Sunsoft International SARL
                    </span>
                </div>
            </div>

            <div class="info-row">
                <div class="check">&#10003;</div>
                <div>
                    <strong>Fichier</strong>
                    <span>__FILENAME__</span>
                </div>
            </div>

        </div>

    </article>


    <article class="panel">

        <h3>
            Téléchargement officiel
        </h3>

        <p>
            Cette page distribue automatiquement
            la dernière version publiée par Sunsoft.
            Une version en brouillon dans
            l'administration n'est jamais proposée
            au public.
        </p>

    </article>

</section>


<footer>
    Sunsoft International SARL
    &middot;
    Sunsoft SECeF
    &middot;
    Distribution officielle
</footer>

</main>

</body>
</html>
"""

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
                "style-src 'unsafe-inline'; "
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
