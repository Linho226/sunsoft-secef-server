from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Vérifie que la plateforme centrale répond."""

    return {
        "status": "ok",
        "service": "sunsoft-secef-server",
    }
