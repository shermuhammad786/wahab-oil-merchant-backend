from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateEntryError, NotFoundError
from app.core.security import hash_password
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def get_by_id(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def list(self) -> list[User]:
        return self.db.scalars(select(User).order_by(User.created_at.desc())).all()

    def create(self, *, name: str, email: str, password: str, role: str = "operator") -> User:
        if self.get_by_email(email):
            raise DuplicateEntryError("User with this email already exists")

        user = User(
            id=f"USR-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user_id: str, payload: dict[str, Any]) -> User:
        user = self.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        for key, value in payload.items():
            if value is not None:
                setattr(user, key, value)
        user.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user_id: str) -> None:
        user = self.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        self.db.delete(user)
        self.db.commit()
