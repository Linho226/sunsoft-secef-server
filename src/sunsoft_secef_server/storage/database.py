from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    Session,
    sessionmaker,
)

from sunsoft_secef_server.storage.models import Base


class Database:
    """Gestion de la base de données du serveur central."""

    def __init__(
        self,
        database_url: str,
    ) -> None:
        normalized_url = database_url.strip()

        if not normalized_url:
            raise ValueError(
                "L'URL de base de données "
                "ne peut pas être vide."
            )

        self.database_url = normalized_url

        self._prepare_sqlite_directory(
            normalized_url
        )

        connect_args = {}

        if normalized_url.startswith(
            "sqlite:"
        ):
            connect_args = {
                "check_same_thread": False,
            }

        self.engine: Engine = create_engine(
            normalized_url,
            future=True,
            connect_args=connect_args,
        )

        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    @staticmethod
    def _prepare_sqlite_directory(
        database_url: str,
    ) -> None:
        prefix = "sqlite:///"

        if not database_url.startswith(prefix):
            return

        database_path = database_url[
            len(prefix):
        ]

        if database_path == ":memory:":
            return

        path = Path(database_path)

        if path.parent != Path("."):
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

    def initialize(self) -> None:
        """Crée le schéma initial de la plateforme."""

        Base.metadata.create_all(
            self.engine
        )

    def session(self) -> Session:
        """Crée une nouvelle session SQLAlchemy."""

        return self._session_factory()

    def dispose(self) -> None:
        """Libère les connexions de la base."""

        self.engine.dispose()