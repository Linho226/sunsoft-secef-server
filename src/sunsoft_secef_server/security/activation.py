import hashlib
import secrets


ACTIVATION_CODE_PREFIX = "SSECFA"

# Alphabet sans caract?res visuellement ambigus.
ACTIVATION_ALPHABET = (
    "ABCDEFGHJKLMNPQRSTUVWXYZ"
    "23456789"
)

ACTIVATION_GROUP_COUNT = 6
ACTIVATION_GROUP_LENGTH = 5


class InvalidActivationCodeError(ValueError):
    """Code d'activation syntaxiquement invalide."""


def generate_activation_code() -> str:
    """
    G?n?re un code d'activation ? usage unique.

    Exemple :
    SSECFA-ABCDE-FGHIJ-KLMNP-QRSTU-VWXYZ-23456

    Seul son hash doit ?tre stock? c?t? serveur.
    """

    groups = []

    for _ in range(
        ACTIVATION_GROUP_COUNT
    ):
        groups.append(
            "".join(
                secrets.choice(
                    ACTIVATION_ALPHABET
                )
                for _ in range(
                    ACTIVATION_GROUP_LENGTH
                )
            )
        )

    return (
        ACTIVATION_CODE_PREFIX
        + "-"
        + "-".join(groups)
    )


def normalize_activation_code(
    code: str,
) -> str:
    """
    Produit la repr?sentation canonique du code.

    Les espaces et tirets sont ignor?s afin de faciliter
    la saisie manuelle depuis le Manager Windows.
    """

    if not isinstance(code, str):
        raise InvalidActivationCodeError(
            "Le code d'activation doit ?tre une cha?ne."
        )

    compact = (
        code.strip()
        .upper()
        .replace("-", "")
        .replace(" ", "")
    )

    expected_length = (
        len(ACTIVATION_CODE_PREFIX)
        + (
            ACTIVATION_GROUP_COUNT
            * ACTIVATION_GROUP_LENGTH
        )
    )

    if len(compact) != expected_length:
        raise InvalidActivationCodeError(
            "Longueur du code d'activation invalide."
        )

    if not compact.startswith(
        ACTIVATION_CODE_PREFIX
    ):
        raise InvalidActivationCodeError(
            "Pr?fixe du code d'activation invalide."
        )

    body = compact[
        len(ACTIVATION_CODE_PREFIX):
    ]

    if any(
        character not in ACTIVATION_ALPHABET
        for character in body
    ):
        raise InvalidActivationCodeError(
            "Caract?re invalide dans le code d'activation."
        )

    return compact


def hash_activation_code(
    code: str,
) -> str:
    """
    Hash SHA-256 de la repr?sentation canonique.

    Le code brut n'est jamais destin? ? ?tre persist?.
    """

    canonical = normalize_activation_code(
        code
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
