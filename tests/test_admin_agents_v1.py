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
            "SUPERVISION DES AGENTS"
            in page.text
        )

        assert (
            "Aucun agent provisionné"
            in page.text
        )


def test_admin_agents_displays_mcf_status_independently_from_agent_presence(
    tmp_path,
):
    """
    La présence de l'Agent et le statut fiscal
    MCF C2 sont deux informations indépendantes.
    """

    import uuid

    from datetime import timedelta

    from sunsoft_secef_server.storage.database import (
        Database,
    )
    from sunsoft_secef_server.storage.models import (
        Agent,
        AgentMCFStatus,
        Tenant,
        utc_now,
    )

    database_url = (
        "sqlite:///"
        + str(
            tmp_path
            / "agents-v1.db"
        )
    )

    database = Database(
        database_url
    )

    database.initialize()

    agent_uid = str(
        uuid.uuid4()
    )

    try:
        with database.session() as session:
            tenant = Tenant(
                tenant_uid=str(
                    uuid.uuid4()
                ),
                name="CLIENT MCF TEST",
            )

            session.add(
                tenant
            )

            session.flush()

            agent = Agent(
                tenant_id=tenant.id,
                agent_uid=agent_uid,
                version="0.2.10",
                environment="test",
                last_seen_at=(
                    utc_now()
                    - timedelta(
                        minutes=10
                    )
                ),
            )

            session.add(
                agent
            )

            session.flush()

            mcf_status = AgentMCFStatus(
                agent_id=agent.id,
                sent_transactions=12,
                available_transactions=88,
                last_connection_datetime=(
                    "20261116093000"
                ),
                connection_age_seconds=3600,
                connection_stale=False,
                last_error=None,
                status_updated_at=utc_now(),
            )

            session.add(
                mcf_status
            )

            session.commit()

    finally:
        database.dispose()

    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:
        _login(
            client
        )

        page = client.get(
            "/admin/agents"
        )

        assert (
            page.status_code
            == 200
        )

        assert (
            "Statut Agent"
            in page.text
        )

        assert (
            "MCF fiscal"
            in page.text
        )

        assert (
            "Dernière C2"
            in page.text
        )

        assert (
            "16/11/2026 09:30:00"
            in page.text
        )

        # Aucun heartbeat Agent :
        # l'Agent est donc hors ligne.
        assert (
            "Hors ligne"
            in page.text
        )

        # Le statut C2 reste néanmoins récent.
        assert (
            "agents-update ok"
            in page.text
        )

        detail = client.get(
            f"/admin/agents/{agent_uid}"
        )

        assert (
            detail.status_code
            == 200
        )

        expected_labels = (
            "MCF fiscal / connexion serveur",
            "État fiscal MCF",
            "Dernière connexion serveur",
            "Ancienneté C2 actuelle",
            "Transactions envoyées",
            "Transactions disponibles",
            "Dernière erreur MCF",
            "Dernier statut C2 reçu",
        )

        for label in expected_labels:
            assert (
                label
                in detail.text
            )

        assert (
            "16/11/2026 09:30:00"
            in detail.text
        )

        compact = (
            detail.text
            .replace(
                "\n",
                "",
            )
            .replace(
                " ",
                "",
            )
        )

        assert (
            ">12<"
            in compact
        )

        assert (
            ">88<"
            in compact
        )

        assert (
            "Aucune"
            in detail.text
        )
