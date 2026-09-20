from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CustomerBase(BaseModel):
    name: str
    phone: str | None = None
    address: str | None = None
    opening_balance: Decimal = Decimal("0.00")
    status: str = "Active"


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    address: str | None = None
    opening_balance: Decimal | None = None
    status: str | None = None


class CustomerRead(CustomerBase):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
