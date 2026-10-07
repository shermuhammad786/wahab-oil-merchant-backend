from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("product_categories.id"), nullable=True, index=True)
    packaging: Mapped[str | None] = mapped_column(String(120), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), default="pcs", nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"), nullable=False)
    current_stock: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0.000"), nullable=False)
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0.000"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    category: Mapped["Category"] = relationship("Category")
