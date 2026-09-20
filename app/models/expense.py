from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subtype: Mapped[str] = mapped_column(String(100), default="Other", nullable=False)
    custom_subtype: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    expense_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(32), default="Cash", nullable=False)
    bank_account_id: Mapped[str | None] = mapped_column(ForeignKey("bank_accounts.id"), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
