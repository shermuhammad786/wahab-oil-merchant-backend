from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError, NotFoundError, ValidationError
from app.models.stock import StockMovement
from app.repositories.stock import StockRepository
from app.schemas.stock import StockAdjustmentRequest, StockBatchAdjustmentRequest


class StockService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = StockRepository(db)

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
        return self.repo.list_movements(
            product_id=product_id,
            movement_type=movement_type,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
            shop_id=shop_id,
        )

    def adjust_stock(self, payload: StockAdjustmentRequest, shop_id: str | None = None) -> StockMovement:
        if payload.quantity <= 0:
            raise ValidationError("Quantity must be greater than zero")
        if payload.direction not in {"increase", "decrease"}:
            raise ValidationError("Direction must be 'increase' or 'decrease'")

        try:
            product = self.repo.get_product_for_update(payload.product_id, shop_id=shop_id)
            if product is None:
                raise NotFoundError("Product not found")
            if product.status == "archived":
                raise ValidationError("Archived products cannot be adjusted")

            current_stock = Decimal(str(product.current_stock))
            quantity = Decimal(str(payload.quantity))

            if payload.direction == "decrease" and quantity > current_stock:
                raise InsufficientStockError("Decrease quantity exceeds current stock")

            new_stock = current_stock + quantity if payload.direction == "increase" else current_stock - quantity
            if new_stock < 0:
                raise InsufficientStockError("Stock cannot go negative")

            product.current_stock = new_stock
            product.updated_at = datetime.utcnow()

            movement = self.repo.create_movement(
                product_id=payload.product_id,
                movement_type=payload.movement_type,
                quantity=quantity,
                previous_stock=current_stock,
                new_stock=new_stock,
                reason=payload.reason,
                note=payload.note,
                reference_type="manual",
                reference_id=None,
                shop_id=shop_id,
            )
            self.db.commit()
            return movement
        except Exception:
            self.db.rollback()
            raise

    def adjust_stock_batch(self, payload: StockBatchAdjustmentRequest, shop_id: str | None = None) -> list[StockMovement]:
        if not payload.adjustments:
            raise ValidationError("At least one adjustment is required")

        seen: set[str] = set()
        for item in payload.adjustments:
            if item.product_id in seen:
                raise ValidationError(f"Duplicate product_id in batch: {item.product_id}")
            seen.add(item.product_id)

        movements: list[StockMovement] = []
        try:
            for item in payload.adjustments:
                if item.quantity <= 0:
                    raise ValidationError(f"Quantity must be greater than zero for product {item.product_id}")
                if item.direction not in {"increase", "decrease"}:
                    raise ValidationError(f"Direction must be 'increase' or 'decrease' for product {item.product_id}")

                product = self.repo.get_product_for_update(item.product_id, shop_id=shop_id)
                if product is None:
                    raise NotFoundError(f"Product not found: {item.product_id}")
                if product.status == "archived":
                    raise ValidationError(f"Archived product cannot be adjusted: {item.product_id}")

                current_stock = Decimal(str(product.current_stock))
                quantity = Decimal(str(item.quantity))
                if item.direction == "decrease" and quantity > current_stock:
                    raise InsufficientStockError(f"Decrease quantity exceeds current stock for product {item.product_id}")

                new_stock = current_stock + quantity if item.direction == "increase" else current_stock - quantity
                if new_stock < 0:
                    raise InsufficientStockError(f"Stock cannot go negative for product {item.product_id}")

                product.current_stock = new_stock
                product.updated_at = datetime.utcnow()

                movement = self.repo.create_movement(
                    product_id=item.product_id,
                    movement_type=item.movement_type,
                    quantity=quantity,
                    previous_stock=current_stock,
                    new_stock=new_stock,
                    reason=item.reason,
                    note=item.note,
                    reference_type="manual",
                    reference_id=None,
                    shop_id=shop_id,
                )
                movements.append(movement)

            self.db.commit()
            return movements
        except Exception:
            self.db.rollback()
            raise
