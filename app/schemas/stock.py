from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from app.core.constants import StockMovementType


class StockAdjustmentRequest(BaseModel):
    product_id: str = Field(validation_alias=AliasChoices("product_id", "productId"))
    direction: str = "increase"
    quantity: Decimal = Field(validation_alias=AliasChoices("quantity", "quantityDelta"), gt=0)
    reason: str | None = None
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def infer_direction(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "direction" not in data and "type" in data:
            data["direction"] = data["type"]
        return data

    @property
    def movement_type(self) -> str:
        return (StockMovementType.MANUAL_IN if self.direction == "increase" else StockMovementType.MANUAL_OUT).value


class StockBatchAdjustmentRequest(BaseModel):
    adjustments: list[StockAdjustmentRequest]


class StockMovementRead(BaseModel):
    id: str
    product_id: str
    product_name: str | None = None
    movement_type: str
    quantity: Decimal
    previous_stock: Decimal
    new_stock: Decimal
    reason: str | None = None
    note: str | None = None
    reference_type: str | None = None
    reference_id: str | None = None
    created_at: datetime
    date: datetime | None = None
    type: str | None = None
    balance: Decimal | None = None
    model_config = ConfigDict(from_attributes=True)
