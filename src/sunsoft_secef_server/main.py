from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import (
    SessionMiddleware,
)

from sunsoft_secef_server import __version__
from sunsoft_secef_server.admin.routes import (
    router as admin_router,
)
from sunsoft_secef_server.admin.security import (
    validate_admin_settings,
)
from sunsoft_secef_server.api.routes.agents import (
    router as agents_router,
)
from sunsoft_secef_server.api.routes.certifications import (
    router as certifications_router,
)
from sunsoft_secef_server.api.routes.health import (
    router as health_router,
)
from sunsoft_secef_server.api.routes.downloads import (
    router as downloads_router,
)
from sunsoft_secef_server.config import (
    Settings,
    get_settings,
)
from sunsoft_secef_server.storage.database import (
    Database,
)


PACKAGE_ROOT = (
    Path(__file__)
    .resolve()
    .parent
)


def create_app(
    settings: Settings | None = None,
) -> FastAPI:
    """Construit l'application centrale Sunsoft SECeF."""

    resolved_settings = (
        settings
        if settings is not None
        else get_settings()
    )

    validate_admin_settings(
        resolved_settings
    )

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ) -> AsyncIterator[None]:
        database = Database(
            resolved_settings.database_url
        )

        database.initialize()

        app.state.database = database
        app.state.settings = resolved_settings

        try:
            yield

        finally:
            database.dispose()

    app = FastAPI(
        title="Sunsoft SECeF Central Server",
        version=__version__,
        lifespan=lifespan,
    )

    if resolved_settings.admin_enabled:
        session_secret = (
            resolved_settings
            .admin_session_secret
        )

        if session_secret is None:
            raise RuntimeError(
                "Secret de session Admin absent."
            )

        app.add_middleware(
            SessionMiddleware,
            secret_key=(
                session_secret
                .get_secret_value()
            ),
            session_cookie=(
                "sunsoft_secef_admin"
            ),
            max_age=(
                resolved_settings
                .admin_session_max_age_seconds
            ),
            same_site="lax",
            https_only=(
                resolved_settings
                .admin_session_https_only
            ),
        )

    app.mount(
        "/admin/static",
        StaticFiles(
            directory=str(
                PACKAGE_ROOT / "static"
            )
        ),
        name="admin-static",
    )

    app.include_router(
        health_router,
        prefix="/api/v1",
    )

    app.include_router(
        agents_router,
        prefix="/api/v1",
    )

    app.include_router(
        certifications_router,
        prefix="/api/v1",
    )

    app.include_router(
        downloads_router,
    )

    app.include_router(
        admin_router,
    )

    return app


app = create_app()