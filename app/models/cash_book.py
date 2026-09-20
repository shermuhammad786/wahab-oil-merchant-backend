from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CashDayClose(Base):
    __tablename__ = "cash_day_closes"

    date: Mapped[datetime] = mapped_column(DateTime, primary_key=True, index=True)
    opening_balance: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    cash_in: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    cash_out: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    closing_balance: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    actual_cash: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 2), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 2), nullable=True)
    finalized_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class CashTransaction(Base):
    __tablename__ = "cash_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    transaction_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
