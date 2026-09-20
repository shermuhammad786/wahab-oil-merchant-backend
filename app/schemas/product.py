from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductBase(BaseModel):
    name: str
    brand: str | None = None
    category_id: str | None = None
    packaging: str | None = None
    unit: str = "pcs"
    purchase_price: float = 0
    sale_price: float = 0
    current_stock: float = 0
    minimum_stock: float = 0
    status: str = "active"


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    name: str | None = None
    unit: str | None = None
    purchase_price: float | None = None
    sale_price: float | None = None
    current_stock: float | None = None
    minimum_stock: float | None = None
    status: str | None = None


class ProductRead(ProductBase):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
