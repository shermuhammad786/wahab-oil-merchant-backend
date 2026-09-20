from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, Token
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    try:
        result = AuthService(db).login(payload.email, payload.password)
        return Token(**result)
    except HTTPException:
        raise


@router.get("/me")
def get_current_user_profile(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
    }


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"status": "ok", "message": "Logged out successfully"}
