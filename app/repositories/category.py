from datetime import datetime
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateEntryError, NotFoundError
from app.models.category import Category


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, search: str = "", shop_id: str | None = None) -> list[Category]:
        query = select(Category).where(Category.is_active.is_(True))
        if shop_id:
            query = query.where(Category.shop_id == shop_id)
        if search:
            q = f"%{search}%"
            query = query.where(Category.name.ilike(q))
        query = query.order_by(Category.name.asc())
        return self.db.scalars(query).all()

    def get_by_name(self, name: str, shop_id: str | None = None) -> Category | None:
        query = self.db.query(Category).filter(Category.name.ilike(name.strip()))
        if shop_id:
            query = query.filter(Category.shop_id == shop_id)
        return query.first()

    def create(self, name: str, shop_id: str | None = None) -> Category:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Category name is required")
        if self.get_by_name(clean_name, shop_id=shop_id):
            raise DuplicateEntryError("Category name already exists")
        category = Category(id=f"CAT-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}", name=clean_name, shop_id=shop_id)
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category
