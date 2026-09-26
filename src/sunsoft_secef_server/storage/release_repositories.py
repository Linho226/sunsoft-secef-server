from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from sunsoft_secef_server.storage.models import (
    AgentRelease,
    utc_now,
)


class AgentReleaseRepositoryError(
    RuntimeError
):
    pass


class AgentReleaseNotFoundError(
    AgentReleaseRepositoryError
):
    pass


class AgentReleaseRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def get_by_uid(
        self,
        release_uid: str,
    ) -> AgentRelease | None:
        statement = select(
            AgentRelease
        ).where(
            AgentRelease.release_uid
            == release_uid.strip()
        )

        return self.session.scalar(
            statement
        )

    def get_by_version(
        self,
        version: str,
    ) -> AgentRelease | None:
        statement = select(
            AgentRelease
        ).where(
            AgentRelease.version
            == version.strip()
        )

        return self.session.scalar(
            statement
        )

    def list_all(
        self,
    ) -> list[AgentRelease]:
        statement = (
            select(AgentRelease)
            .order_by(
                AgentRelease.created_at.desc()
            )
        )

        return list(
            self.session.scalars(
                statement
            )
        )

    def get_current(
        self,
    ) -> AgentRelease | None:
        statement = (
            select(AgentRelease)
            .where(
                AgentRelease.is_published.is_(
                    True
                ),
                AgentRelease.archived_at.is_(
                    None
                ),
            )
            .order_by(
                AgentRelease.published_at.desc(),
                AgentRelease.created_at.desc(),
            )
            .limit(1)
        )

        return self.session.scalar(
            statement
        )

    def create(
        self,
        *,
        version: str,
        filename: str,
        storage_path: str,
        sha256: str,
        file_size: int,
        release_notes: str | None = None,
    ) -> AgentRelease:

        normalized_version = version.strip()
        normalized_filename = filename.strip()
        normalized_path = storage_path.strip()
        normalized_sha256 = sha256.strip().lower()

        if not normalized_version:
            raise ValueError(
                "Version obligatoire."
            )

        if not normalized_filename:
            raise ValueError(
                "Nom de fichier obligatoire."
            )

        if not normalized_path:
            raise ValueError(
                "Chemin de stockage obligatoire."
            )

        if (
            len(normalized_sha256) != 64
            or any(
                c not in "0123456789abcdef"
                for c in normalized_sha256
            )
        ):
            raise ValueError(
                "SHA-256 invalide."
            )

        if (
            isinstance(file_size, bool)
            or not isinstance(
                file_size,
                int,
            )
            or file_size <= 0
        ):
            raise ValueError(
                "Taille de fichier invalide."
            )

        if self.get_by_version(
            normalized_version
        ) is not None:
            raise AgentReleaseRepositoryError(
                "Cette version existe d?j?."
            )

        release = AgentRelease(
            release_uid=str(
                uuid.uuid4()
            ),
            version=normalized_version,
            filename=normalized_filename,
            storage_path=normalized_path,
            sha256=normalized_sha256,
            file_size=file_size,
            release_notes=(
                release_notes.strip()
                if release_notes
                else None
            ),
            is_published=False,
        )

        self.session.add(
            release
        )

        self.session.flush()

        return release

    def publish(
        self,
        release_uid: str,
    ) -> AgentRelease:

        release = self.get_by_uid(
            release_uid
        )

        if release is None:
            raise AgentReleaseNotFoundError(
                "Version Agent introuvable."
            )

        if release.archived_at is not None:
            raise AgentReleaseRepositoryError(
                "Une version archiv?e "
                "ne peut pas ?tre publi?e."
            )

        current_releases = list(
            self.session.scalars(
                select(
                    AgentRelease
                ).where(
                    AgentRelease.is_published.is_(
                        True
                    )
                )
            )
        )

        for current in current_releases:
            current.is_published = False

        release.is_published = True
        release.published_at = utc_now()

        self.session.flush()

        return release

    def archive(
        self,
        release_uid: str,
    ) -> AgentRelease:

        release = self.get_by_uid(
            release_uid
        )

        if release is None:
            raise AgentReleaseNotFoundError(
                "Version Agent introuvable."
            )

        release.is_published = False

        if release.archived_at is None:
            release.archived_at = utc_now()

        self.session.flush()

        return release
