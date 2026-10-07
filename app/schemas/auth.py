from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    email: str
    password: str
    shop_id: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class TokenPayload(BaseModel):
    sub: str
    shop_id: str
    role: str = "operator"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    shop_id: str | None = None
    role: str | None = None
    shop_name: str | None = None
    model_config = ConfigDict(from_attributes=True)
