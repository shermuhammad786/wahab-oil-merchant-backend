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

    def login(self, email: str, password: str) -> dict[str, str]:
        user = UserRepository(self.db).get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")

        token = create_access_token(subject=user.email, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
        return {"access_token": token, "token_type": "bearer"}
