import hashlib
import re

from fastapi.testclient import TestClient

from sunsoft_secef_server.admin.security import (
    hash_password,
)
from sunsoft_secef_server.config import Settings
from sunsoft_secef_server.main import create_app


PASSWORD = "Admin-Test-Password-2026"


def settings_for(
    tmp_path,
):

    return Settings(
        environment="test",
        database_url=(
            "sqlite:///"
            + str(
                tmp_path / "public.db"
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
            "public-test-secret-"
            "0123456789abcdef"
            "0123456789abcdef"
        ),
        admin_session_https_only=False,
        agent_release_storage_dir=str(
            tmp_path / "releases"
        ),
    )


def csrf_from(
    html,
):

    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        html,
    )

    assert match is not None

    return match.group(1)


def login(
    client,
):

    page = client.get(
        "/admin/login"
    )

    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token":
                csrf_from(page.text),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_public_agent_portal(
    tmp_path,
):

    app = create_app(
        settings_for(
            tmp_path
        )
    )

    payload = (
        b"MZ"
        + b"\x90" * 256
        + b"SUNSOFT-SECEF-PUBLIC"
    )

    sha = hashlib.sha256(
        payload
    ).hexdigest()

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        # Public, sans connexion.
        page = client.get(
            "/agent"
        )

        assert page.status_code == 200
        assert "Sunsoft SECeF Agent" in page.text
        assert "Aucune version disponible" in page.text

        before = client.get(
            "/download/agent"
        )

        assert before.status_code == 404

        # Administration.
        login(client)

        admin = client.get(
            "/admin/agent-windows"
        )

        uploaded = client.post(
            "/admin/agent-windows",
            data={
                "version": "1.2.3",
                "release_notes":
                    "Version publique de test.",
                "csrf_token":
                    csrf_from(admin.text),
            },
            files={
                "installer": (
                    "Sunsoft-SECeF-Agent-Setup.exe",
                    payload,
                    "application/octet-stream",
                )
            },
            follow_redirects=False,
        )

        assert uploaded.status_code == 303

        admin = client.get(
            "/admin/agent-windows"
        )

        publish = re.search(
            r'action="'
            r'(?:https?://[^"]+)?'
            r'(/admin/agent-windows/'
            r'[^"]+/publish)'
            r'"',
            admin.text,
        )

        assert publish is not None

        published = client.post(
            publish.group(1),
            data={
                "csrf_token":
                    csrf_from(admin.text),
            },
            follow_redirects=False,
        )

        assert published.status_code == 303

        # Toujours public sans login spécifique.
        page = client.get(
            "/agent"
        )

        assert page.status_code == 200
        assert "Version 1.2.3" in page.text
        assert "Version publique de test." in page.text
        assert sha.upper() in page.text
        assert 'href="/download/agent"' in page.text

        download = client.get(
            "/download/agent"
        )

        assert download.status_code == 200
        assert download.content == payload

        assert (
            download.headers[
                "x-sunsoft-secef-version"
            ]
            == "1.2.3"
        )

        assert (
            download.headers[
                "x-sunsoft-secef-sha256"
            ]
            == sha
        )
