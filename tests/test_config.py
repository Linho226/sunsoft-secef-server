from sunsoft_secef_server.config import Settings


def test_default_settings() -> None:
    settings = Settings(
        _env_file=None,
    )

    assert settings.environment == "development"
    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert (
        settings.database_url
        == "sqlite:///server_data/server.db"
    )
    assert settings.log_level == "INFO"


def test_settings_can_be_loaded_from_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SECEF_SERVER_ENVIRONMENT",
        "test",
    )
    monkeypatch.setenv(
        "SECEF_SERVER_HOST",
        "0.0.0.0",
    )
    monkeypatch.setenv(
        "SECEF_SERVER_PORT",
        "9100",
    )
    monkeypatch.setenv(
        "SECEF_SERVER_DATABASE_URL",
        "sqlite:///custom_data/custom.db",
    )
    monkeypatch.setenv(
        "SECEF_SERVER_LOG_LEVEL",
        "DEBUG",
    )

    settings = Settings(
        _env_file=None,
    )

    assert settings.environment == "test"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9100
    assert (
        settings.database_url
        == "sqlite:///custom_data/custom.db"
    )
    assert settings.log_level == "DEBUG"