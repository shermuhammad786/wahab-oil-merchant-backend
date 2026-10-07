from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, Token
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    try:
        result = AuthService(db).login(payload.email, payload.password, shop_id=payload.shop_id)
        return Token(**result)
    except HTTPException:
        raise


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    if not payload.current_password or not payload.new_password or not payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password, new password, and confirmation are required")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters long")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password and confirmation do not match")
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    user = db.get(User, current_user.id)
    if user is None or user.shop_id != current_user.shop_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authenticated user shop mismatch")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return {"status": "ok", "message": "Password changed successfully"}


@router.get("/me")
def get_current_user_profile(current_user: User = Depends(get_current_user)) -> dict:
    shop_name = current_user.shop.name if current_user.shop else current_user.shop_id
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "shop_id": current_user.shop_id,
        "shop_name": shop_name,
        "is_active": current_user.is_active,
    }


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"status": "ok", "message": "Logged out successfully"}
