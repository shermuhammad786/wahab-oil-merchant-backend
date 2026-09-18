from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class UserCreate(BaseModel):

    name: str = Field(
        ...,
        min_length=2,
        max_length=100
    )

    email: EmailStr

    password: str = Field(
        ...,
        min_length=8,
        max_length=100
    )

    age: int = Field(
        ...,
        ge=13,
        le=120
    )

    phone: str | None = Field(
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


class UserResponse(BaseModel):

    id: int
    name: str
    email: EmailStr
    age: int
    phone: str | None
    is_active: bool