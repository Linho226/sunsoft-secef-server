from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sunsoft_secef_server import __version__
from sunsoft_secef_server.api.routes.agents import (
    router as agents_router,
)
from sunsoft_secef_server.api.routes.health import (
    router as health_router,
)
from sunsoft_secef_server.config import (
    Settings,
    get_settings,
)
from sunsoft_secef_server.storage.database import (
    Database,
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

    app.include_router(
        health_router,
        prefix="/api/v1",
    )

    app.include_router(
        agents_router,
        prefix="/api/v1",
    )

    return app


app = create_app()