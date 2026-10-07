from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
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

    def get_by_id(self, product_id: str, shop_id: str | None = None) -> Product | None:
        query = select(Product).where(Product.id == product_id)
        if shop_id:
            query = query.where(Product.shop_id == shop_id)
        return self.db.scalar(query)

    def list(self, include_archived: bool = False, search: str = "", status: str = "", page: int = 1, page_size: int = 500, shop_id: str | None = None) -> list[Product]:
        query = select(Product)
        if shop_id:
            query = query.where(Product.shop_id == shop_id)
        if not include_archived:
            query = query.where(Product.status != "archived")
        if search:
            pattern = f"%{search}%"
            query = query.where(or_(Product.name.ilike(pattern), Product.id.ilike(pattern)))
        if status and status.lower() not in {"all", ""}:
            query = query.where(Product.status == status.lower().replace(" ", "_"))
        query = query.order_by(Product.created_at.desc())
        return self.db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()

    def has_transaction_history(self, product_id: str, shop_id: str | None = None) -> bool:
        query = (
            self.db.query(SaleItem.id).filter(SaleItem.product_id == product_id)
            or self.db.query(PurchaseItem.id).filter(PurchaseItem.product_id == product_id)
            or self.db.query(StockMovement.id).filter(StockMovement.product_id == product_id)
            or self.db.query(SaleReturnItem.id).filter(SaleReturnItem.product_id == product_id)
            or self.db.query(PurchaseReturnItem.id).filter(PurchaseReturnItem.product_id == product_id)
        )
        if shop_id:
            query = query.filter(SaleItem.shop_id == shop_id) if False else query
        return (
            self.db.query(SaleItem.id).filter(SaleItem.product_id == product_id, SaleItem.shop_id == shop_id if shop_id else True).first() is not None
            or self.db.query(PurchaseItem.id).filter(PurchaseItem.product_id == product_id, PurchaseItem.shop_id == shop_id if shop_id else True).first() is not None
            or self.db.query(StockMovement.id).filter(StockMovement.product_id == product_id, StockMovement.shop_id == shop_id if shop_id else True).first() is not None
            or self.db.query(SaleReturnItem.id).filter(SaleReturnItem.product_id == product_id, SaleReturnItem.shop_id == shop_id if shop_id else True).first() is not None
            or self.db.query(PurchaseReturnItem.id).filter(PurchaseReturnItem.product_id == product_id, PurchaseReturnItem.shop_id == shop_id if shop_id else True).first() is not None
        )

    def archive(self, product_id: str, shop_id: str | None = None) -> Product:
        product = self.get_by_id(product_id, shop_id=shop_id)
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

    def update(self, product_id: str, payload: dict[str, Any], shop_id: str | None = None) -> Product:
        product = self.get_by_id(product_id, shop_id=shop_id)
        if not product:
            raise NotFoundError("Product not found")

        for key, value in payload.items():
            if value is not None:
                setattr(product, key, value)
        product.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(product)
        return product

    def delete(self, product_id: str, shop_id: str | None = None) -> None:
        product = self.get_by_id(product_id, shop_id=shop_id)
        if not product:
            raise NotFoundError("Product not found")
        self.db.delete(product)
        self.db.commit()
