from datetime import datetime, timezone

from fastapi.testclient import TestClient

from sunsoft_secef_server.admin.security import (
    hash_password,
)
from sunsoft_secef_server.config import Settings
from sunsoft_secef_server.main import create_app
from sunsoft_secef_server.storage.release_repositories import (
    AgentReleaseRepository,
)


PASSWORD = "Admin-Test-Password-2026"


def settings_for(tmp_path):
    return Settings(
        environment="test",
        database_url=(
            "sqlite:///"
            + str(tmp_path / "release-api.db")
        ),
        admin_enabled=True,
        admin_username="admin",
        admin_password_hash=(
            hash_password(
                PASSWORD,
                iterations=1000,
            )
        ),
        admin_session_secret=(
            "release-api-test-secret-"
            "0123456789abcdef"
            "0123456789abcdef"
        ),
        admin_session_https_only=False,
        agent_release_storage_dir=str(
            tmp_path / "releases"
        ),
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def test_latest_release_returns_current_published_release(
    tmp_path,
):
    app = create_app(
        settings_for(tmp_path)
    )

    with TestClient(app) as client:
        database = app.state.database

        with database.session() as session:
            repo = AgentReleaseRepository(
                session
            )

            release = repo.create(
                version="0.2.6",
                filename=(
                    "Sunsoft-SECeF-Agent-Setup-0.2.6.exe"
                ),
                storage_path=(
                    "releases/agent/0.2.6/"
                    "Sunsoft-SECeF-Agent-Setup-0.2.6.exe"
                ),
                sha256="a" * 64,
                file_size=54735892,
                release_notes=(
                    "Ajout du mécanisme de mise à jour."
                ),
            )

            repo.publish(
                release.release_uid
            )

            session.commit()

            assert release.published_at is not None

            expected_published_at = _utc(
                release.published_at
            )

        response = client.get(
            "/api/v1/agent/releases/latest"
        )

        assert response.status_code == 200

        payload = response.json()

        assert set(payload) == {
            "version",
            "filename",
            "sha256",
            "file_size",
            "download_url",
            "release_notes",
            "published_at",
        }

        assert payload["version"] == "0.2.6"

        assert payload["filename"] == (
            "Sunsoft-SECeF-Agent-Setup-0.2.6.exe"
        )

        assert payload["sha256"] == (
            "a" * 64
        )

        assert payload["file_size"] == 54735892

        assert payload["download_url"] == (
            "/download/agent"
        )

        assert payload["release_notes"] == (
            "Ajout du mécanisme de mise à jour."
        )

        assert payload["published_at"] is not None

        actual_published_at = datetime.fromisoformat(
            payload["published_at"].replace(
                "Z",
                "+00:00",
            )
        )

        assert (
            _utc(actual_published_at)
            == expected_published_at
        )


def test_latest_release_returns_explicit_404_without_release(
    tmp_path,
):
    app = create_app(
        settings_for(tmp_path)
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/agent/releases/latest"
        )

        assert response.status_code == 404

        assert response.json() == {
            "detail": (
                "Aucune version Agent "
                "n'est actuellement publiee."
            )
        }
