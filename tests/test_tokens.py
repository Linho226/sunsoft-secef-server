import pytest

from sunsoft_secef_server.security.tokens import (
    AGENT_TOKEN_PREFIX,
    ODOO_TOKEN_PREFIX,
    InvalidTokenError,
    generate_agent_token,
    generate_odoo_token,
    get_token_kind,
    hash_token,
    token_fingerprint,
    verify_token,
)


def test_generate_agent_token() -> None:
    first = generate_agent_token()
    second = generate_agent_token()

    assert first.startswith(
        AGENT_TOKEN_PREFIX
    )

    assert second.startswith(
        AGENT_TOKEN_PREFIX
    )

    assert first != second

    assert (
        get_token_kind(first)
        == "agent"
    )


def test_generate_odoo_token() -> None:
    token = generate_odoo_token()

    assert token.startswith(
        ODOO_TOKEN_PREFIX
    )

    assert (
        get_token_kind(token)
        == "odoo"
    )


def test_hash_and_verify_token() -> None:
    token = generate_agent_token()

    token_hash = hash_token(
        token
    )

    assert len(token_hash) == 64

    assert verify_token(
        token,
        token_hash,
    ) is True


def test_wrong_token_is_rejected() -> None:
    token = generate_agent_token()

    other_token = generate_agent_token()

    token_hash = hash_token(
        token
    )

    assert verify_token(
        other_token,
        token_hash,
    ) is False


def test_invalid_token_prefix_is_rejected() -> None:
    with pytest.raises(
        InvalidTokenError
    ):
        get_token_kind(
            "invalid-token"
        )


def test_token_fingerprint_is_not_secret() -> None:
    token = generate_odoo_token()

    fingerprint = token_fingerprint(
        token
    )

    assert len(fingerprint) == 12

    assert fingerprint != token

    assert token not in fingerprint