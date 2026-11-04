from fastapi import APIRouter

from sunsoft_secef_server.api.auth import (
    OdooAuthDependency,
)


router = APIRouter(
    prefix="/odoo",
    tags=["odoo"],
)


@router.post("/heartbeat")
def odoo_heartbeat(
    credential: OdooAuthDependency,
) -> dict[str, str]:
    """
    Enregistre la pr?sence r?cente d'une instance Odoo.

    La date last_used_at est mise ? jour pendant
    l'authentification du credential Odoo.
    """

    return {
        "status": "ok",
        "credential_uid": credential.credential_uid,
    }
