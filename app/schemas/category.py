from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CategoryBase(BaseModel):
    name: str
    is_active: bool = True


class CategoryCreate(BaseModel):
    name: str


class CategoryRead(CategoryBase):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
