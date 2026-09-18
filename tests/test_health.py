from fastapi.testclient import TestClient

from sunsoft_secef_server.main import create_app


def test_health() -> None:
    client = TestClient(
        create_app()
    )

    response = client.get(
        "/api/v1/health"
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
        "service": "sunsoft-secef-server",
    }
