from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateEntryError, ValidationError
from app.models.category import Category
from app.repositories.category import CategoryRepository
from app.schemas.category import CategoryCreate


class CategoryService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CategoryRepository(db)

    def create_category(self, payload: CategoryCreate, shop_id: str | None = None) -> Category:
        name = (payload.name or "").strip()
        if not name:
            raise ValidationError("Category name is required")
        try:
            return self.repo.create(name, shop_id=shop_id)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        except DuplicateEntryError:
            raise
