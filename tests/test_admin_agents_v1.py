from datetime import (
    datetime,
    timedelta,
    timezone,
)
import re

from fastapi.testclient import TestClient

from sunsoft_secef_server.admin.routes import (
    _agent_is_online,
    _agent_update_state,
)
from sunsoft_secef_server.admin.security import (
    hash_password,
)
from sunsoft_secef_server.config import Settings
from sunsoft_secef_server.main import create_app


PASSWORD = "Admin-Test-Password-2026"


def _settings(tmp_path):

    return Settings(
        environment="test",
        database_url=(
            "sqlite:///"
            + str(
                tmp_path / "agents-v1.db"
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
            "agents-v1-test-secret-"
            "0123456789abcdef"
            "0123456789abcdef"
        ),
        admin_session_https_only=False,
        agent_release_storage_dir=str(
            tmp_path / "releases"
        ),
    )


def _csrf(html):

    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        html,
    )

    assert match is not None

    return match.group(1)


def _login(client):

    page = client.get(
        "/admin/login"
    )

    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token":
                _csrf(page.text),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_agent_online_state():

    now = datetime.now(
        timezone.utc
    )

    assert _agent_is_online(
        now - timedelta(seconds=179),
        now=now,
    )

    assert not _agent_is_online(
        now - timedelta(seconds=181),
        now=now,
    )


def test_agent_update_state():

    assert _agent_update_state(
        "0.2.0",
        "0.2.0",
    ) == (
        "À jour",
        "ok",
    )

    assert _agent_update_state(
        "0.1.0",
        "0.2.0",
    ) == (
        "Mise à jour disponible",
        "warning",
    )


def test_agents_admin_v1_page(
    tmp_path,
):

    app = create_app(
        _settings(tmp_path)
    )

    detail_path = str(
        app.url_path_for(
            "admin-agent-detail",
            agent_uid=(
                "00000000-0000-0000-"
                "0000-000000000001"
            ),
        )
    )

    assert detail_path.startswith(
        "/admin/agents/"
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        unauth = client.get(
            "/admin/agents"
        )

        assert unauth.status_code == 303

        _login(client)

        page = client.get(
            "/admin/agents"
        )

        assert page.status_code == 200

        assert (
            "Agents Windows"
            in page.text
        )

        assert (
            "SUPERVISION AGENTS"
            in page.text
        )

        assert (
            "Aucun Agent provisionné"
            in page.text
        )

        assert (
            "Fonctionnalités complémentaires"
            in page.text
        )
