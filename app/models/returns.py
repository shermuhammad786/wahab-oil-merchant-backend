from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SaleReturn(Base):
    __tablename__ = "sale_returns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id"), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    return_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class SaleReturnItem(Base):
    __tablename__ = "sale_return_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    return_id: Mapped[str] = mapped_column(ForeignKey("sale_returns.id"), nullable=False)
    sale_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(18, 3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)


class PurchaseReturn(Base):
    __tablename__ = "purchase_returns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    purchase_id: Mapped[str] = mapped_column(ForeignKey("purchases.id"), nullable=False)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    return_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class PurchaseReturnItem(Base):
    __tablename__ = "purchase_return_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    return_id: Mapped[str] = mapped_column(ForeignKey("purchase_returns.id"), nullable=False)
    purchase_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(18, 3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
