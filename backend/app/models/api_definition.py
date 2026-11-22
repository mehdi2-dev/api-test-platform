"""Test edilecek bir API isteğinin tanımı (ATOP-22).

Bir tanım; adres (URL), metod, header'lar, query parametreleri, body ve kimlik
doğrulama bilgisinden oluşur. Kimlik doğrulamadaki gizli değerler (token, şifre,
API anahtarı) auth_config_encrypted sütununda şifreli tutulur.
"""

from enum import StrEnum

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class BodyType(StrEnum):
    NONE = "none"
    JSON = "json"
    TEXT = "text"


class AuthType(StrEnum):
    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"
    API_KEY = "api_key"


def _values(enum_cls: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_cls]


class ApiDefinition(TimestampMixin, Base):
    __tablename__ = "api_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    method: Mapped[HttpMethod] = mapped_column(
        Enum(HttpMethod, name="http_method", values_callable=_values), default=HttpMethod.GET
    )
    url: Mapped[str] = mapped_column(String(2048))

    # [{"key": "Accept", "value": "application/json", "enabled": true}, ...]
    headers: Mapped[list] = mapped_column(JSON, default=list)
    query_params: Mapped[list] = mapped_column(JSON, default=list)

    body_type: Mapped[BodyType] = mapped_column(
        Enum(BodyType, name="body_type", values_callable=_values), default=BodyType.NONE
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    auth_type: Mapped[AuthType] = mapped_column(
        Enum(AuthType, name="auth_type", values_callable=_values), default=AuthType.NONE
    )
    auth_config_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
