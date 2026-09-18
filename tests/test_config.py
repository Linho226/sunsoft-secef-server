from sunsoft_secef_server.config import Settings


def test_default_settings() -> None:
    settings = Settings(
        _env_file=None,
    )

    assert settings.environment == "development"
    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert settings.log_level == "INFO"
