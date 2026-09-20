from fastapi import APIRouter

from app.db.session import check_db_connection

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "Wahab Oil Merchant"}


@router.get("/health/db")
def health_db_check() -> dict[str, bool | str]:
    connected = check_db_connection()
    return {"status": "ok" if connected else "error", "database": connected}
