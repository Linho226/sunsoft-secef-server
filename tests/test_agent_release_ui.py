import hashlib
import re

from fastapi.testclient import (
    TestClient,
)

from sunsoft_secef_server.admin.security import (
    hash_password,
)
from sunsoft_secef_server.config import (
    Settings,
)
from sunsoft_secef_server.main import (
    create_app,
)


PASSWORD = (
    "Admin-Test-Password-2026"
)


def _settings(
    tmp_path,
):
    return Settings(
        environment="test",
        database_url=(
            "sqlite:///"
            + str(
                tmp_path
                / "agent-release-ui.db"
            )
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
            "test-session-secret-"
            "0123456789abcdef"
            "0123456789abcdef"
        ),
        admin_session_https_only=False,
        agent_release_storage_dir=str(
            tmp_path
            / "agent-releases"
        ),
    )


def _csrf(
    html: str,
) -> str:

    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        html,
    )

    assert match is not None

    return match.group(1)


def _login(
    client,
):

    page = client.get(
        "/admin/login"
    )

    csrf = _csrf(
        page.text
    )

    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_agent_release_admin_lifecycle(
    tmp_path,
):

    app = create_app(
        _settings(
            tmp_path
        )
    )

    installer_bytes = (
        b"MZ"
        + b"\x90" * 256
        + b"SUNSOFT-SECEF-TEST"
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        _login(
            client
        )

        page = client.get(
            "/admin/agent-windows"
        )

        assert page.status_code == 200

        assert (
            "Agent Windows"
            in page.text
        )

        csrf = _csrf(
            page.text
        )

        uploaded = client.post(
            "/admin/agent-windows",
            data={
                "version": "1.0.0",
                "release_notes": (
                    "Version de test."
                ),
                "csrf_token": csrf,
            },
            files={
                "installer": (
                    "Sunsoft-SECeF-Agent-Setup.exe",
                    installer_bytes,
                    "application/octet-stream",
                ),
            },
            follow_redirects=False,
        )

        assert uploaded.status_code == 303

        page = client.get(
            "/admin/agent-windows"
        )

        assert page.status_code == 200

        assert "1.0.0" in page.text

        expected_sha = hashlib.sha256(
            installer_bytes
        ).hexdigest()

        assert (
            expected_sha
            in page.text
        )

        publish_match = re.search(
            r'action="'
            r'(?:https?://[^"]+)?'
            r'(/admin/agent-windows/'
            r'[^"]+/publish)'
            r'"',
            page.text,
        )

        assert publish_match is not None

        csrf = _csrf(
            page.text
        )

        published = client.post(
            publish_match.group(1),
            data={
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        assert published.status_code == 303

        public_download = client.get(
            "/download/agent"
        )

        assert public_download.status_code == 200

        assert (
            public_download.content
            == installer_bytes
        )

        assert (
            public_download.headers[
                "x-sunsoft-secef-version"
            ]
            == "1.0.0"
        )

        assert (
            public_download.headers[
                "x-sunsoft-secef-sha256"
            ]
            == expected_sha
        )

        assert (
            "Sunsoft-SECeF-Agent-Setup.exe"
            in public_download.headers[
                "content-disposition"
            ]
        )

        page = client.get(
            "/admin/agent-windows"
        )

        archive_match = re.search(
            r'action="'
            r'(?:https?://[^"]+)?'
            r'(/admin/agent-windows/'
            r'[^"]+/archive)'
            r'"',
            page.text,
        )

        assert archive_match is not None

        csrf = _csrf(
            page.text
        )

        archived = client.post(
            archive_match.group(1),
            data={
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        assert archived.status_code == 303

        unavailable = client.get(
            "/download/agent"
        )

        assert unavailable.status_code == 404
