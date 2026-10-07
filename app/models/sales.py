from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.money import ZERO_MONEY
from app.db.base import Base


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("shop_id", "invoice_number", name="uq_sales_shop_invoice_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    sale_type: Mapped[str] = mapped_column(String(32), default="installment", nullable=False)
    sale_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    total: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    paid: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    remaining: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
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

    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    sale_id: Mapped[str] = mapped_column(ForeignKey("sales.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(18, 3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)

    sale: Mapped[Sale] = relationship(back_populates="items")
