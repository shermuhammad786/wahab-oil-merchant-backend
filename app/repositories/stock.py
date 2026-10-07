from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError, NotFoundError
from app.models.product import Product
from app.models.stock import StockMovement


class StockRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_product_for_update(self, product_id: str, shop_id: str | None = None) -> Product | None:
        query = select(Product).where(Product.id == product_id)
        if shop_id:
            query = query.where(Product.shop_id == shop_id)
        return self.db.execute(query.with_for_update()).scalar_one_or_none()

    def list_movements(
        self,
        *,
        product_id: str | None = None,
        movement_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        page_size: int = 50,
        shop_id: str | None = None,
    ) -> list[StockMovement]:
        query = select(StockMovement)
        if shop_id:
            query = query.where(StockMovement.shop_id == shop_id)
        if product_id:
            query = query.where(StockMovement.product_id == product_id)
        if movement_type:
            query = query.where(StockMovement.movement_type == movement_type)
        if date_from:
            query = query.where(StockMovement.created_at >= datetime.fromisoformat(date_from))
        if date_to:
            query = query.where(StockMovement.created_at <= datetime.fromisoformat(date_to))
        query = query.order_by(StockMovement.created_at.desc())
        if page and page_size:
            query = query.offset((page - 1) * page_size).limit(page_size)
        return self.db.scalars(query).all()

    def create_movement(
        self,
        *,
        product_id: str,
        movement_type: str,
        quantity: Decimal,
        previous_stock: Decimal,
        new_stock: Decimal,
        reason: str | None = None,
        note: str | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
        shop_id: str | None = None,
    ) -> StockMovement:
        movement = StockMovement(
            id=f"STM-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            product_id=product_id,
            shop_id=shop_id,
            movement_type=movement_type,
            quantity=quantity,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reason=reason,
            note=note,
            reference_type=reference_type,
            reference_id=reference_id,
            created_at=datetime.utcnow(),
        )
        self.db.add(movement)
        self.db.flush()
        return movement

    def update_product_stock(self, product_id: str, new_stock: Decimal, shop_id: str | None = None) -> Product:
        product = self.get_product_for_update(product_id, shop_id=shop_id)
        if product is None:
            raise NotFoundError("Product not found")
        product.current_stock = new_stock
        product.updated_at = datetime.utcnow()
        self.db.flush()
        return product
