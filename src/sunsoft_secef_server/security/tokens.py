import hashlib
import secrets
from hmac import compare_digest
from typing import Final, Literal


TokenKind = Literal[
    "agent",
    "odoo",
]


AGENT_TOKEN_PREFIX: Final = "ssecf_agent_"
ODOO_TOKEN_PREFIX: Final = "ssecf_odoo_"

TOKEN_RANDOM_BYTES: Final = 32

TOKEN_HASH_LENGTH: Final = 64


class TokenError(ValueError):
    """Erreur liée à un token SECeF."""


class InvalidTokenError(TokenError):
    """Token invalide ou mal formé."""


def _normalize_token(
    token: str,
) -> str:
    """Normalise et valide un token opaque."""

    if not isinstance(token, str):
        raise TypeError(
            "Le token doit être une chaîne."
        )

    normalized_token = token.strip()

    if not normalized_token:
        raise InvalidTokenError(
            "Le token ne peut pas être vide."
        )

    return normalized_token


def generate_token(
    kind: TokenKind,
) -> str:
    """
    Génère un token cryptographiquement aléatoire.

    Le token complet est destiné à être affiché une
    seule fois au client. Seule son empreinte doit
    ensuite être stockée en base.
    """

    if kind == "agent":
        prefix = AGENT_TOKEN_PREFIX

    elif kind == "odoo":
        prefix = ODOO_TOKEN_PREFIX

    else:
        raise ValueError(
            "Type de token non supporté."
        )

    random_part = secrets.token_urlsafe(
        TOKEN_RANDOM_BYTES
    )

    return f"{prefix}{random_part}"


def generate_agent_token() -> str:
    """Génère un token destiné à un Agent Windows."""

    return generate_token(
        "agent"
    )


def generate_odoo_token() -> str:
    """Génère un token destiné à une instance Odoo."""

    return generate_token(
        "odoo"
    )


def hash_token(
    token: str,
) -> str:
    """
    Calcule l'empreinte SHA-256 d'un token.

    Les tokens sont générés avec suffisamment
    d'entropie pour permettre un stockage sûr de
    leur empreinte sans conserver le secret brut.
    """

    normalized_token = _normalize_token(
        token
    )

    return hashlib.sha256(
        normalized_token.encode(
            "utf-8"
        )
    ).hexdigest()


def verify_token(
    token: str,
    expected_hash: str,
) -> bool:
    """Compare un token à une empreinte stockée."""

    normalized_token = _normalize_token(
        token
    )

    if not isinstance(
        expected_hash,
        str,
    ):
        raise TypeError(
            "expected_hash doit être une chaîne."
        )

    normalized_hash = (
        expected_hash.strip().lower()
    )

    if len(normalized_hash) != TOKEN_HASH_LENGTH:
        return False

    actual_hash = hash_token(
        normalized_token
    )

    return compare_digest(
        actual_hash,
        normalized_hash,
    )


def get_token_kind(
    token: str,
) -> TokenKind:
    """Détermine le type d'un token SECeF."""

    normalized_token = _normalize_token(
        token
    )

    if normalized_token.startswith(
        AGENT_TOKEN_PREFIX
    ):
        return "agent"

    if normalized_token.startswith(
        ODOO_TOKEN_PREFIX
    ):
        return "odoo"

    raise InvalidTokenError(
        "Préfixe de token SECeF invalide."
    )


def token_fingerprint(
    token: str,
) -> str:
    """
    Produit un identifiant court non secret.

    Il peut être utilisé ultérieurement dans les logs
    sans exposer le token d'authentification.
    """

    digest = hash_token(
        token
    )

    return digest[:12]