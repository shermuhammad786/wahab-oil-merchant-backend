from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateEntryError, NotFoundError
from app.models.product import Product
from app.models.purchases import PurchaseItem
from app.models.returns import PurchaseReturnItem, SaleReturnItem
from app.models.sales import SaleItem
from app.models.stock import StockMovement


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, product_id: str) -> Product | None:
        return self.db.get(Product, product_id)

    def list(self, include_archived: bool = False) -> list[Product]:
        query = select(Product)
        if not include_archived:
            query = query.where(Product.status != "archived")
        query = query.order_by(Product.created_at.desc())
        return self.db.scalars(query).all()

    def has_transaction_history(self, product_id: str) -> bool:
        return (
            self.db.query(SaleItem.id).filter(SaleItem.product_id == product_id).first() is not None
            or self.db.query(PurchaseItem.id).filter(PurchaseItem.product_id == product_id).first() is not None
            or self.db.query(StockMovement.id).filter(StockMovement.product_id == product_id).first() is not None
            or self.db.query(SaleReturnItem.id).filter(SaleReturnItem.product_id == product_id).first() is not None
            or self.db.query(PurchaseReturnItem.id).filter(PurchaseReturnItem.product_id == product_id).first() is not None
        )

    def archive(self, product_id: str) -> Product:
        product = self.get_by_id(product_id)
        if not product:
            raise NotFoundError("Product not found")
        product.status = "archived"
        product.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(product)
        return product

    def create(self, **payload: Any) -> Product:
        product = Product(
            id=f"PRD-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            **payload,
        )
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def update(self, product_id: str, payload: dict[str, Any]) -> Product:
        product = self.get_by_id(product_id)
        if not product:
            raise NotFoundError("Product not found")

        for key, value in payload.items():
            if value is not None:
                setattr(product, key, value)
        product.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(product)
        return product

    def delete(self, product_id: str) -> None:
        product = self.get_by_id(product_id)
        if not product:
            raise NotFoundError("Product not found")
        self.db.delete(product)
        self.db.commit()
