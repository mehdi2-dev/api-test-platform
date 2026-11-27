from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr = Field(examples=["admin@apitest.com"])
    # bcrypt en fazla 72 bayt şifre kabul eder
    password: str = Field(min_length=1, max_length=72, examples=["Admin12345"])


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token'ın kaç saniye geçerli olduğu")
