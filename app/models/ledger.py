from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.money import ZERO_MONEY
from app.db.base import Base


class CustomerLedgerEntry(Base):
    __tablename__ = "customer_ledger_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    sale_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    payment_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    return_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SupplierLedgerEntry(Base):
    __tablename__ = "supplier_ledger_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    purchase_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    payment_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    return_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=ZERO_MONEY, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
