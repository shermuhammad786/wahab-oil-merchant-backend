from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailyPaymentRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    reference: str | None = None
    notes: str | None = None


class DailySupplierPaymentRow(DailyPaymentRow):
    supplier_id: str = Field(alias="supplierId", min_length=1)


class DailyCustomerPaymentRow(DailyPaymentRow):
    customer_id: str = Field(alias="customerId", min_length=1)


class DailySupplierPayments(BaseModel):
    date: date
    payments: list[DailySupplierPaymentRow] = Field(min_length=1)


class DailyCustomerPayments(BaseModel):
    date: date
    payments: list[DailyCustomerPaymentRow] = Field(min_length=1)
