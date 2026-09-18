from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from sunsoft_secef_server.storage.database import Database


def get_database(
    request: Request,
) -> Database:
    """Retourne la base centrale attachée à FastAPI."""

    database = getattr(
        request.app.state,
        "database",
        None,
    )

    if database is None:
        raise RuntimeError(
            "La base centrale n'est pas initialisée."
        )

    return database


def get_session(
    request: Request,
) -> Generator[Session, None, None]:
    """Fournit une transaction SQLAlchemy à une requête."""

    database = get_database(
        request
    )

    with database.session() as session:
        try:
            yield session
            session.commit()

        except Exception:
            session.rollback()
            raise