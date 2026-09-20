from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerPayment(Base):
    __tablename__ = "customer_payments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    payment_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sale_id: Mapped[str | None] = mapped_column(ForeignKey("sales.id"), nullable=True)
    bank_account_id: Mapped[str | None] = mapped_column(ForeignKey("bank_accounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class SupplierPayment(Base):
    __tablename__ = "supplier_payments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    payment_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    purchase_id: Mapped[str | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    bank_account_id: Mapped[str | None] = mapped_column(ForeignKey("bank_accounts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
