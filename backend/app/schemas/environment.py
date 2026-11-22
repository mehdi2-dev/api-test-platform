"""Ortam ve değişken şemaları (ATOP-27, ATOP-30)."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.variables import VARIABLE_NAME

VARIABLE_PATTERN = f"^{VARIABLE_NAME}$"


class VariableIn(BaseModel):
    key: str = Field(
        min_length=1,
        max_length=100,
        pattern=VARIABLE_PATTERN,
        description="Harf veya _ ile başlar; harf, rakam, _ . - içerebilir",
    )
    value: str = Field(default="", max_length=10_000)
    is_secret: bool = False


class VariableRead(BaseModel):
    key: str
    value: str = Field(description="Gizli değişkenlerde ******** döner")
    is_secret: bool


def _unique_keys(items: list[VariableIn] | None) -> list[VariableIn] | None:
    if items is None:
        return None
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        if item.key in seen:
            duplicates.add(item.key)
        seen.add(item.key)
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise ValueError(f"Aynı değişken birden fazla kez tanımlanmış: {names}")
    return items


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_production: bool = False
    variables: list[VariableIn] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ortam adı boş olamaz")
        return value

    @field_validator("variables")
    @classmethod
    def check_keys(cls, value: list[VariableIn]) -> list[VariableIn]:
        return _unique_keys(value)


class EnvironmentUpdate(BaseModel):
    """Gönderilen alanlar değişir. variables gönderilirse listenin tamamı yerine geçer."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    is_production: bool | None = None
    variables: list[VariableIn] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Ortam adı boş olamaz")
        return value

    @field_validator("variables")
    @classmethod
    def check_keys(cls, value: list[VariableIn] | None) -> list[VariableIn] | None:
        return _unique_keys(value)


class EnvironmentRead(BaseModel):
    id: int
    name: str
    description: str | None
    is_production: bool
    variables: list[VariableRead]
    created_at: datetime
    updated_at: datetime


class SendOptions(BaseModel):
    """'Gönder' isteğinin isteğe bağlı ayarları."""

    environment_id: int | None = Field(
        default=None, description="Değişkenlerin alınacağı ortam; boşsa ortamsız gönderilir"
    )
    confirm_production: bool = Field(
        default=False,
        description="Production ortamında veri değiştiren (POST/PUT/PATCH/DELETE) istek için onay",
    )
