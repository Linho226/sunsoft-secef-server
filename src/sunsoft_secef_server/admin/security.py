from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Request

from sunsoft_secef_server.config import Settings


PASSWORD_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 310_000


def hash_password(
    password: str,
    *,
    iterations: int = DEFAULT_ITERATIONS,
) -> str:
    """Construit un hash PBKDF2-SHA256 pour le compte Admin."""

    if not isinstance(password, str):
        raise TypeError(
            "password doit être une chaîne."
        )

    if len(password) < 12:
        raise ValueError(
            "Le mot de passe Admin doit contenir "
            "au moins 12 caractères."
        )

    salt = os.urandom(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )

    return (
        f"{PASSWORD_SCHEME}"
        f"${iterations}"
        f"${salt.hex()}"
        f"${digest.hex()}"
    )


def verify_password(
    password: str,
    encoded_hash: str,
) -> bool:
    """Vérifie un mot de passe sans comparaison temporelle naïve."""

    try:
        scheme, iterations_text, salt_hex, digest_hex = (
            encoded_hash.split("$", 3)
        )

        if scheme != PASSWORD_SCHEME:
            return False

        iterations = int(
            iterations_text
        )

        salt = bytes.fromhex(
            salt_hex
        )

        expected = bytes.fromhex(
            digest_hex
        )

    except (
        AttributeError,
        TypeError,
        ValueError,
    ):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )

    return hmac.compare_digest(
        actual,
        expected,
    )


def validate_admin_settings(
    settings: Settings,
) -> None:
    """Refuse une configuration Admin incomplète."""

    if not settings.admin_enabled:
        return

    username = (
        settings.admin_username
        or ""
    ).strip()

    if not username:
        raise RuntimeError(
            "SECEF_SERVER_ADMIN_USERNAME est obligatoire."
        )

    if not settings.admin_password_hash:
        raise RuntimeError(
            "SECEF_SERVER_ADMIN_PASSWORD_HASH "
            "est obligatoire."
        )

    if not settings.admin_password_hash.startswith(
        PASSWORD_SCHEME + "$"
    ):
        raise RuntimeError(
            "SECEF_SERVER_ADMIN_PASSWORD_HASH "
            "a un format invalide."
        )

    secret = settings.admin_session_secret

    if secret is None:
        raise RuntimeError(
            "SECEF_SERVER_ADMIN_SESSION_SECRET "
            "est obligatoire."
        )

    raw_secret = secret.get_secret_value()

    if len(raw_secret) < 32:
        raise RuntimeError(
            "SECEF_SERVER_ADMIN_SESSION_SECRET "
            "doit contenir au moins 32 caractères."
        )


def ensure_csrf_token(
    request: Request,
) -> str:
    """Retourne le token CSRF de la session."""

    token = request.session.get(
        "csrf_token"
    )

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)

        request.session[
            "csrf_token"
        ] = token

    return token


def verify_csrf_token(
    request: Request,
    submitted: str,
) -> bool:
    """Compare le CSRF soumis à celui de la session."""

    expected = request.session.get(
        "csrf_token"
    )

    if not isinstance(expected, str):
        return False

    if not isinstance(submitted, str):
        return False

    return secrets.compare_digest(
        expected,
        submitted,
    )


def is_admin_authenticated(
    request: Request,
) -> bool:
    """Indique si la session courante est Admin."""

    return (
        request.session.get(
            "admin_authenticated"
        )
        is True
    )