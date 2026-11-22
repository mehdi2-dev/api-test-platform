from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


def _fits_bcrypt(password: str) -> str:
    # bcrypt en fazla 72 bayt kabul eder; Türkçe harfler (ş, ğ, ı...) 2 bayt sayılır
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Şifre çok uzun (en fazla 72 bayt)")
    return password


NewPassword = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_fits_bcrypt)]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    password: NewPassword
    role: Role = Role.VIEWER


class UserUpdate(BaseModel):
    """Sadece gönderilen alanlar değişir; gönderilmeyenler olduğu gibi kalır."""

    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: NewPassword | None = None
    role: Role | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    """Kullanıcı bilgisi; şifre özeti dışarıya asla verilmez."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
