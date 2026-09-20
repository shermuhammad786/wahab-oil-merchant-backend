from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import StockMovementType


class StockAdjustmentRequest(BaseModel):
    product_id: str
    direction: str
    quantity: Decimal = Field(..., gt=0)
    reason: str | None = None
    note: str | None = None

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
    model_config = ConfigDict(from_attributes=True)
