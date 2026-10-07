from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str
    category_id: str | None = None
    purchase_price: Decimal = Decimal("0.00")
    current_stock: Decimal = Decimal("0.000")
    minimum_stock: Decimal = Decimal("0.000")
    status: str = "active"


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    category_id: str | None = None
    purchase_price: Decimal | None = None
    minimum_stock: Decimal | None = None
    status: str | None = None


class ProductRead(ProductBase):
    id: str
    category: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
