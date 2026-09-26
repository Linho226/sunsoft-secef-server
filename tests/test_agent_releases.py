from sunsoft_secef_server.storage.database import (
    Database,
)

from sunsoft_secef_server.storage.release_repositories import (
    AgentReleaseRepository,
)


def test_agent_release_lifecycle(
    tmp_path,
):
    database = Database(
        "sqlite:///"
        + str(
            tmp_path
            / "agent-releases.db"
        )
    )

    database.initialize()

    with database.session() as session:

        repo = AgentReleaseRepository(
            session
        )

        first = repo.create(
            version="1.0.0",
            filename=(
                "Sunsoft-SECeF-Agent-Setup.exe"
            ),
            storage_path=(
                "releases/agent/"
                "1.0.0/"
                "Sunsoft-SECeF-Agent-Setup.exe"
            ),
            sha256="a" * 64,
            file_size=123456,
            release_notes="Premi?re version.",
        )

        session.commit()

        assert first.is_published is False

        repo.publish(
            first.release_uid
        )

        session.commit()

        current = repo.get_current()

        assert current is not None
        assert current.version == "1.0.0"
        assert current.is_published is True


        second = repo.create(
            version="1.1.0",
            filename=(
                "Sunsoft-SECeF-Agent-Setup.exe"
            ),
            storage_path=(
                "releases/agent/"
                "1.1.0/"
                "Sunsoft-SECeF-Agent-Setup.exe"
            ),
            sha256="b" * 64,
            file_size=234567,
        )

        repo.publish(
            second.release_uid
        )

        session.commit()

        current = repo.get_current()

        assert current is not None
        assert current.version == "1.1.0"

        refreshed_first = repo.get_by_uid(
            first.release_uid
        )

        assert refreshed_first is not None
        assert refreshed_first.is_published is False


        repo.archive(
            second.release_uid
        )

        session.commit()

        assert repo.get_current() is None

        archived = repo.get_by_uid(
            second.release_uid
        )

        assert archived is not None
        assert archived.archived_at is not None
        assert archived.is_published is False

    database.dispose()
