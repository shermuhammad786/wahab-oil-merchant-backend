from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    movement_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(18, 3), nullable=False)
    previous_stock: Mapped[Decimal] = mapped_column(DECIMAL(18, 3), default=Decimal("0.000"), nullable=False)
    new_stock: Mapped[Decimal] = mapped_column(DECIMAL(18, 3), default=Decimal("0.000"), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    product: Mapped["Product"] = relationship("Product")
