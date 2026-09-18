from fastapi import FastAPI

from sunsoft_secef_server import __version__
from sunsoft_secef_server.api.routes.health import (
    router as health_router,
)


def create_app() -> FastAPI:
    """Construit l'application FastAPI centrale."""

    app = FastAPI(
        title="Sunsoft SECeF Central Server",
        version=__version__,
    )

    app.include_router(
        health_router,
        prefix="/api/v1",
    )

    return app


app = create_app()
