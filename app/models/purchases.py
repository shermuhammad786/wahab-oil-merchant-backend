from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    purchase_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    purchase_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    paid: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=0, nullable=False)
    remaining: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=0, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    items: Mapped[list["PurchaseItem"]] = relationship(back_populates="purchase", cascade="all, delete-orphan")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    purchase_id: Mapped[str] = mapped_column(ForeignKey("purchases.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(18, 3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)

    purchase: Mapped[Purchase] = relationship(back_populates="items")
