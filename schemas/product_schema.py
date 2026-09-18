from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class ProductCreate(BaseModel):

    name: str = Field(
        ...,
        min_length=2,
        max_length=100
    )

    purchase_price: str = Field(
        ...,
        min_length=2,
        max_length=100,
    )

    category: str | None = Field(
        default=None,
        max_length=20
    )

    opening_stock: str | None = Field(
        default=None,
        max_length=20
    )
    
    minimum_stock: str | None = Field(
        default=None,
        max_length=20
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):

        value = value.strip()

        if not re.fullmatch(r"[A-Za-z ]+", value):
            raise ValueError(
                "Name can contain only letters and spaces"
            )

        return value



class UserUpdate(BaseModel):

    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100
    )

    address: str | None = Field(
        default=None,
        min_length=2,
        max_length=100
    )

    phone: str | None = Field(
        default=None,
        max_length=20
    )

    type: str | None = Field(
        default=None,
        max_length=20
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):

        if value is None:
            return value

        value = value.strip()

        if not re.fullmatch(r"[A-Za-z ]+", value):
            raise ValueError(
                "Name can contain only letters and spaces"
            )

        return value


class UserResponse(BaseModel):

    id: int
    name: str
    address: str
    phone: str | None
    is_active: bool