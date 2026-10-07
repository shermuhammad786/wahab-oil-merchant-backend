from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.repositories.user import UserRepository

settings = get_settings()


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def login(self, email: str, password: str, shop_id: str | None = None) -> dict[str, str | None]:
        user = UserRepository(self.db).get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
        if shop_id and user.shop_id != shop_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User does not belong to the requested shop")

        token = create_access_token(
            subject=user.email,
            shop_id=user.shop_id,
            role=user.role,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "shop_id": user.shop_id,
            "role": user.role,
            "shop_name": user.shop.name if user.shop else user.shop_id,
        }
