import uvicorn

from sunsoft_secef_server.config import get_settings


def main() -> None:
    """Lance le serveur central."""

    settings = get_settings()

    uvicorn.run(
        "sunsoft_secef_server.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
