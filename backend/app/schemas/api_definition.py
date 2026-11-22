"""API tanımı için giriş/çıkış şemaları (ATOP-22, ATOP-24).

Gizli değerler (token, password, key_value) cevaplarda asla açık dönmez, yerine
MASK yazılır. Güncellemede MASK geri gönderilirse kayıtlı değer korunur; yani
arayüz gizli değeri bilmeden formu kaydedebilir.
"""

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.api_definition import AuthType, BodyType, HttpMethod
from app.schemas.assertion import Assertion

MASK = "********"
SECRET_FIELDS = ("token", "password", "key_value")


class KeyValue(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    value: str = Field(default="", max_length=4000)
    enabled: bool = True


class AuthConfig(BaseModel):
    """Kimlik doğrulama ayarı. Hangi alanların dolu olacağı type'a göre değişir.

    - none:    alan yok
    - bearer:  token
    - basic:   username, password
    - api_key: key_name, key_value, location (header veya query)
    """

    type: AuthType = AuthType.NONE
    token: str | None = Field(default=None, max_length=4000)
    username: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=500)
    key_name: str | None = Field(default=None, max_length=200)
    key_value: str | None = Field(default=None, max_length=4000)
    location: Literal["header", "query"] = "header"

    @model_validator(mode="after")
    def check_required_fields(self) -> "AuthConfig":
        required = {
            AuthType.NONE: (),
            AuthType.BEARER: ("token",),
            AuthType.BASIC: ("username", "password"),
            AuthType.API_KEY: ("key_name", "key_value"),
        }[self.type]
        missing = [name for name in required if not getattr(self, name)]
        if missing:
            raise ValueError(f"{self.type.value} için zorunlu alan eksik: {', '.join(missing)}")
        return self

    def stored_fields(self) -> dict[str, Any]:
        """Veritabanına (şifreli) yazılacak alanlar: sadece bu tipe ait olanlar."""
        fields = {
            AuthType.NONE: (),
            AuthType.BEARER: ("token",),
            AuthType.BASIC: ("username", "password"),
            AuthType.API_KEY: ("key_name", "key_value", "location"),
        }[self.type]
        return {name: getattr(self, name) for name in fields}


def masked_auth(auth_type: AuthType, stored: dict[str, Any]) -> AuthConfig:
    """Kayıtlı ayarı, gizli alanları maskelenmiş olarak döndürür."""
    data = {
        key: (MASK if key in SECRET_FIELDS and value else value) for key, value in stored.items()
    }
    return AuthConfig.model_construct(type=auth_type, **data)


def check_json_body(body_type: BodyType, body: str | None) -> None:
    if body_type == BodyType.JSON and body and body.strip():
        try:
            json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Body geçerli bir JSON değil (satır {exc.lineno}, sütun {exc.colno}): {exc.msg}"
            ) from exc


def _check_url(value: str) -> str:
    value = value.strip()
    # {{base_url}}/users gibi ortam değişkeniyle başlayan adreslere de izin veriyoruz (Epic 4)
    if not value.startswith(("http://", "https://", "{{")):
        raise ValueError("URL http:// veya https:// ile başlamalı")
    return value


class ApiDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    method: HttpMethod = HttpMethod.GET
    url: str = Field(min_length=1, max_length=2048)
    headers: list[KeyValue] = Field(default_factory=list)
    query_params: list[KeyValue] = Field(default_factory=list)
    body_type: BodyType = BodyType.NONE
    body: str | None = Field(default=None, max_length=1_000_000)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    assertions: list[Assertion] = Field(default_factory=list, max_length=100)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        return _check_url(value)

    @model_validator(mode="after")
    def check_body(self) -> "ApiDefinitionCreate":
        check_json_body(self.body_type, self.body)
        return self


class ApiDefinitionUpdate(BaseModel):
    """Sadece gönderilen alanlar değişir."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    method: HttpMethod | None = None
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    headers: list[KeyValue] | None = None
    query_params: list[KeyValue] | None = None
    body_type: BodyType | None = None
    body: str | None = Field(default=None, max_length=1_000_000)
    auth: AuthConfig | None = None
    assertions: list[Assertion] | None = Field(default=None, max_length=100)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str | None) -> str | None:
        return None if value is None else _check_url(value)


class ApiDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    method: HttpMethod
    url: str
    headers: list[KeyValue]
    query_params: list[KeyValue]
    body_type: BodyType
    body: str | None
    auth: AuthConfig
    assertions: list[Assertion]
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime


class SentRequest(BaseModel):
    """Gerçekte gönderilen isteğin özeti (gizli değerler maskeli)."""

    method: str
    url: str
    headers: dict[str, str]


class SendResult(BaseModel):
    """'Gönder' sonucu (ATOP-26)."""

    ok: bool = Field(description="Cevap alındıysa true (durum kodu ne olursa olsun)")
    status_code: int | None = None
    elapsed_ms: float = Field(description="İstek başından cevabın sonuna kadar geçen süre (ms)")
    size_bytes: int = 0
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    body_json: Any | None = Field(default=None, description="Cevap JSON ise ayrıştırılmış hali")
    truncated: bool = Field(default=False, description="Body çok uzun olduğu için kısaltıldı mı")
    error: str | None = Field(default=None, description="Cevap alınamadıysa nedeni")
    environment: str | None = Field(default=None, description="Kullanılan ortamın adı")
    request: SentRequest
