from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CashCreditPerson(Base):
    __tablename__ = "cash_credit_people"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_cash_given: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=0, nullable=False)
    total_received: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class CashCreditTransaction(Base):
    __tablename__ = "cash_credit_transactions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("cash_credit_people.id"), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
