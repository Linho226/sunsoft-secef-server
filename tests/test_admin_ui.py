import re

from fastapi.testclient import TestClient

from sunsoft_secef_server.admin.security import (
    hash_password,
)
from sunsoft_secef_server.config import Settings
from sunsoft_secef_server.main import create_app


def _settings(tmp_path):
    return Settings(
        environment="test",
        database_url=(
            "sqlite:///"
            + str(
                tmp_path
                / "admin-ui-test.db"
            )
        ),
        admin_enabled=True,
        admin_username="admin",
        admin_password_hash=(
            hash_password(
                "Admin-Test-Password-2026"
            )
        ),
        admin_session_secret=(
            "test-session-secret-"
            "0123456789abcdef"
            "0123456789abcdef"
        ),
        admin_session_https_only=False,
    )


def _csrf(html: str) -> str:
    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        html,
    )

    assert match is not None

    return match.group(1)


def test_admin_requires_authentication(
    tmp_path,
):
    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:
        response = client.get(
            "/admin"
        )

        assert response.status_code == 303
        assert response.headers[
            "location"
        ] == "/admin/login"


def test_admin_login_and_empty_dashboard(
    tmp_path,
):
    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        login = client.get(
            "/admin/login"
        )

        assert login.status_code == 200
        assert "Sunsoft SECeF" in login.text

        csrf = _csrf(
            login.text
        )

        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": (
                    "Admin-Test-Password-2026"
                ),
                "csrf_token": csrf,
            },
        )

        assert response.status_code == 303
        assert response.headers[
            "location"
        ] == "/admin"

        dashboard = client.get(
            "/admin"
        )

        assert dashboard.status_code == 200
        assert "Tableau de bord" in dashboard.text
        assert "Clients" in dashboard.text
        assert "Sites" in dashboard.text
        assert "Agents" in dashboard.text
        assert "Activations" in dashboard.text

        for path in (
            "/admin/clients",
            "/admin/sites",
            "/admin/agents",
            "/admin/activations",
        ):
            page = client.get(
                path
            )

            assert page.status_code == 200


def test_admin_rejects_wrong_password(
    tmp_path,
):
    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(app) as client:

        login = client.get(
            "/admin/login"
        )

        csrf = _csrf(
            login.text
        )

        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": "wrong-password",
                "csrf_token": csrf,
            },
        )

        assert response.status_code == 401
        assert (
            "Identifiants invalides"
            in response.text
        )


def test_admin_disabled_by_default(
    tmp_path,
    monkeypatch,
):
    admin_environment_variables = (
        "SECEF_SERVER_ADMIN_ENABLED",
        "SECEF_SERVER_ADMIN_USERNAME",
        "SECEF_SERVER_ADMIN_PASSWORD_HASH",
        "SECEF_SERVER_ADMIN_SESSION_SECRET",
        "SECEF_SERVER_ADMIN_SESSION_HTTPS_ONLY",
        "SECEF_SERVER_ADMIN_SESSION_MAX_AGE_SECONDS",
    )

    for variable in admin_environment_variables:
        monkeypatch.delenv(
            variable,
            raising=False,
        )

    settings = Settings(
        environment="test",
        database_url=(
            "sqlite:///"
            + str(
                tmp_path
                / "disabled.db"
            )
        ),
    )

    app = create_app(
        settings
    )

    with TestClient(app) as client:
        response = client.get(
            "/admin/login"
        )

        assert response.status_code == 404


def test_admin_can_create_client(
    tmp_path,
):
    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        login = client.get(
            "/admin/login"
        )

        csrf = _csrf(
            login.text
        )

        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": (
                    "Admin-Test-Password-2026"
                ),
                "csrf_token": csrf,
            },
        )

        assert response.status_code == 303

        page = client.get(
            "/admin/clients"
        )

        csrf = _csrf(
            page.text
        )

        response = client.post(
            "/admin/clients",
            data={
                "name": (
                    "SUNSOFT INTERNATIONAL SARL"
                ),
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        assert response.status_code == 303

        page = client.get(
            "/admin/clients"
        )

        assert (
            "SUNSOFT INTERNATIONAL SARL"
            in page.text
        )



def test_admin_can_create_site(
    tmp_path,
):
    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        login = client.get(
            "/admin/login"
        )

        csrf = _csrf(
            login.text
        )

        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": (
                    "Admin-Test-Password-2026"
                ),
                "csrf_token": csrf,
            },
        )

        assert response.status_code == 303


        clients = client.get(
            "/admin/clients"
        )

        csrf = _csrf(
            clients.text
        )

        response = client.post(
            "/admin/clients",
            data={
                "name": "SITE TEST CLIENT",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        assert response.status_code == 303


        sites = client.get(
            "/admin/sites"
        )

        csrf = _csrf(
            sites.text
        )

        import re

        match = re.search(
            r'<option\s+value="([^"]+)"[^>]*>\s*'
            r'SITE TEST CLIENT\s*</option>',
            sites.text,
        )

        assert match is not None

        tenant_uid = match.group(1)


        response = client.post(
            "/admin/sites",
            data={
                "tenant_uid": tenant_uid,
                "code": "SIEGE",
                "name": "Siege Ouagadougou",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        assert response.status_code == 303


        sites = client.get(
            "/admin/sites"
        )

        assert "Siege Ouagadougou" in sites.text
        assert "SIEGE" in sites.text
        assert "SITE TEST CLIENT" in sites.text



def test_admin_can_generate_activation(
    tmp_path,
):
    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        login = client.get(
            "/admin/login"
        )

        csrf = _csrf(
            login.text
        )

        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": (
                    "Admin-Test-Password-2026"
                ),
                "csrf_token": csrf,
            },
        )

        assert response.status_code == 303


        clients = client.get(
            "/admin/clients"
        )

        csrf = _csrf(
            clients.text
        )

        client.post(
            "/admin/clients",
            data={
                "name": "ACTIVATION TEST CLIENT",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )


        sites = client.get(
            "/admin/sites"
        )

        csrf = _csrf(
            sites.text
        )

        import re

        tenant_match = re.search(
            r'<option\s+value="([^"]+)"[^>]*>\s*'
            r'ACTIVATION TEST CLIENT\s*</option>',
            sites.text,
        )

        assert tenant_match is not None

        tenant_uid = tenant_match.group(1)


        client.post(
            "/admin/sites",
            data={
                "tenant_uid": tenant_uid,
                "code": "SIEGE",
                "name": "Siege Test",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )


        activation_page = client.get(
            "/admin/activations"
        )

        assert activation_page.status_code == 200

        csrf = _csrf(
            activation_page.text
        )


        site_match = re.search(
            r'<option\s+'
            r'value="([^"]+)"\s+'
            r'data-tenant="'
            + re.escape(tenant_uid)
            + r'"',
            activation_page.text,
        )

        assert site_match is not None

        site_uid = site_match.group(1)


        generated = client.post(
            "/admin/activations",
            data={
                "tenant_uid": tenant_uid,
                "site_uid": site_uid,
                "expires_in_minutes": "60",
                "csrf_token": csrf,
            },
        )

        assert generated.status_code == 200

        assert (
            "Code g&eacute;n&eacute;r&eacute; avec succ&egrave;s"
            in generated.text
        )

        assert (
            'id="activation-code"'
            in generated.text
        )

        assert (
            "ACTIVATION TEST CLIENT"
            in generated.text
        )

        assert "code_hash" not in generated.text


        history = client.get(
            "/admin/activations"
        )

        assert history.status_code == 200

        assert (
            "ACTIVATION TEST CLIENT"
            in history.text
        )

        assert "SIEGE" in history.text
        assert "Disponible" in history.text



def test_dashboard_after_activation_sqlite(
    tmp_path,
):
    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        login = client.get(
            "/admin/login"
        )

        csrf = _csrf(
            login.text
        )

        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": (
                    "Admin-Test-Password-2026"
                ),
                "csrf_token": csrf,
            },
        )

        assert response.status_code == 303


        clients = client.get(
            "/admin/clients"
        )

        csrf = _csrf(
            clients.text
        )

        client.post(
            "/admin/clients",
            data={
                "name": "DASHBOARD TEST CLIENT",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )


        sites = client.get(
            "/admin/sites"
        )

        csrf = _csrf(
            sites.text
        )

        import re

        tenant_match = re.search(
            r'<option\s+value="([^"]+)"[^>]*>\s*'
            r'DASHBOARD TEST CLIENT\s*</option>',
            sites.text,
        )

        assert tenant_match is not None

        tenant_uid = tenant_match.group(1)


        client.post(
            "/admin/sites",
            data={
                "tenant_uid": tenant_uid,
                "code": "SIEGE",
                "name": "Dashboard Site",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )


        activations = client.get(
            "/admin/activations"
        )

        csrf = _csrf(
            activations.text
        )

        site_match = re.search(
            r'<option\s+'
            r'value="([^"]+)"\s+'
            r'data-tenant="'
            + re.escape(tenant_uid)
            + r'"',
            activations.text,
        )

        assert site_match is not None

        site_uid = site_match.group(1)


        generated = client.post(
            "/admin/activations",
            data={
                "tenant_uid": tenant_uid,
                "site_uid": site_uid,
                "expires_in_minutes": "60",
                "csrf_token": csrf,
            },
        )

        assert generated.status_code == 200


        dashboard = client.get(
            "/admin"
        )

        assert dashboard.status_code == 200

        assert "Tableau de bord" in dashboard.text
        assert "Disponible" in dashboard.text



def test_admin_can_revoke_activation(
    tmp_path,
):
    app = create_app(
        _settings(tmp_path)
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        import re

        # Login
        login = client.get(
            "/admin/login"
        )

        csrf = _csrf(
            login.text
        )

        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": (
                    "Admin-Test-Password-2026"
                ),
                "csrf_token": csrf,
            },
        )

        assert response.status_code == 303


        # Client
        page = client.get(
            "/admin/clients"
        )

        csrf = _csrf(
            page.text
        )

        client.post(
            "/admin/clients",
            data={
                "name": "REVOKE TEST CLIENT",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )


        # Site
        page = client.get(
            "/admin/sites"
        )

        csrf = _csrf(
            page.text
        )

        tenant_match = re.search(
            r'<option\s+value="([^"]+)"[^>]*>\s*'
            r'REVOKE TEST CLIENT\s*</option>',
            page.text,
        )

        assert tenant_match is not None

        tenant_uid = tenant_match.group(1)

        client.post(
            "/admin/sites",
            data={
                "tenant_uid": tenant_uid,
                "code": "SIEGE",
                "name": "Revoke Site",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )


        # Activation
        page = client.get(
            "/admin/activations"
        )

        csrf = _csrf(
            page.text
        )

        site_match = re.search(
            r'<option\s+'
            r'value="([^"]+)"\s+'
            r'data-tenant="'
            + re.escape(tenant_uid)
            + r'"',
            page.text,
        )

        assert site_match is not None

        site_uid = site_match.group(1)

        generated = client.post(
            "/admin/activations",
            data={
                "tenant_uid": tenant_uid,
                "site_uid": site_uid,
                "expires_in_minutes": "60",
                "csrf_token": csrf,
            },
        )

        assert generated.status_code == 200
        assert "Disponible" in generated.text


        # Route de r?vocation pr?sente
        revoke_match = re.search(
            r'action="'
            r'(?:https?://[^"]+)?'
            r'(/admin/activations/[^"]+/revoke)'
            r'"',
            generated.text,
        )

        assert revoke_match is not None

        revoke_url = revoke_match.group(1)

        csrf = _csrf(
            generated.text
        )


        # R?vocation
        revoked = client.post(
            revoke_url,
            data={
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        assert revoked.status_code == 303

        assert revoked.headers[
            "location"
        ] == "/admin/activations"


        # V?rification
        page = client.get(
            "/admin/activations"
        )

        assert page.status_code == 200

        assert "Inactif" in page.text
