"""Test edilecek bir API isteğinin tanımı ve ona ait kurallar.

Bir tanım; adres (URL), metod, header'lar, query parametreleri, body ve kimlik
doğrulama bilgisinden oluşur. Kimlik doğrulamadaki gizli değerler (token, şifre,
API anahtarı) şifreli tutulur; şifrelemeyi use case'in verdiği fonksiyon yapar.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.domain.environments import Environment
from app.domain.errors import InvalidInput, ProductionConfirmationRequired, SecretUnreadable
from app.domain.secrets import MASK


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


# Veri değiştirebilen metodlar: Production ortamında açık onay ister
MUTATING_METHODS = frozenset({HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH, HttpMethod.DELETE})
# Cevaplarda MASK ile gizlenen kimlik bilgisi alanları
SECRET_AUTH_FIELDS = ("token", "password", "key_value")


def check_json_body(body_type: BodyType | None, body: str | None) -> None:
    """Body tipi JSON ise içerik geçerli JSON olmalı."""
    if body_type == BodyType.JSON and body and body.strip():
        try:
            json.loads(body)
        except json.JSONDecodeError as exc:
            raise InvalidInput(
                f"Body geçerli bir JSON değil (satır {exc.lineno}, sütun {exc.colno}): {exc.msg}"
            ) from exc


def ensure_production_confirmed(
    environment: Environment, method: HttpMethod, confirmed: bool
) -> None:
    """Production ortamında veri değiştiren istek, açık onay olmadan gönderilmez."""
    if environment.is_production and method in MUTATING_METHODS and not confirmed:
        raise ProductionConfirmationRequired(
            f"'{environment.name}' bir Production ortamı ve {method.value} "
            "isteği gerçek verileri değiştirebilir. Emin misiniz?"
        )


@dataclass(eq=False, kw_only=True)
class ApiDefinition:
    name: str
    url: str
    description: str | None = None
    method: HttpMethod = HttpMethod.GET
    # [{"key": "Accept", "value": "application/json", "enabled": true}, ...]
    headers: list[dict[str, Any]] = field(default_factory=list)
    query_params: list[dict[str, Any]] = field(default_factory=list)
    body_type: BodyType = BodyType.NONE
    body: str | None = None
    auth_type: AuthType = AuthType.NONE
    auth_config_encrypted: str | None = field(default=None, repr=False)
    # Test kuralları: [{"type": "status_code", "operator": "equals", ...}, ...]
    assertions: list[dict[str, Any]] = field(default_factory=list)
    created_by_id: int | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_mutating(self) -> bool:
        return self.method in MUTATING_METHODS

    def stored_auth(self, decrypt: Callable[[str], str]) -> dict[str, Any]:
        """Kayıtlı kimlik bilgisi alanlarını çözülmüş halde döndürür."""
        if not self.auth_config_encrypted:
            return {}
        try:
            return json.loads(decrypt(self.auth_config_encrypted))
        except SecretUnreadable as exc:
            raise SecretUnreadable(
                "Kimlik bilgisi çözülemedi; şifreleme anahtarı değişmiş olabilir"
            ) from exc

    def change_auth(
        self,
        auth_type: AuthType,
        fields: dict[str, Any],
        *,
        encrypt: Callable[[str], str],
        decrypt: Callable[[str], str],
    ) -> None:
        """Kimlik bilgisini şifreleyip kaydeder.

        Gizli bir alan için MASK gelirse kayıtlı değer korunur; ancak kayıtlı değer
        yoksa veya kimlik doğrulama tipi değiştiyse yeni değer girilmelidir.
        """
        previous = self.stored_auth(decrypt)
        fields = dict(fields)
        for name in SECRET_AUTH_FIELDS:
            if fields.get(name) == MASK:
                if not previous.get(name) or auth_type != self.auth_type:
                    raise InvalidInput(f"'{name}' için kayıtlı değer yok, lütfen yeni değer girin")
                fields[name] = previous[name]

        self.auth_type = auth_type
        self.auth_config_encrypted = (
            encrypt(json.dumps(fields, ensure_ascii=False)) if auth_type != AuthType.NONE else None
        )

    def apply_changes(self, changes: dict[str, Any]) -> None:
        """Gönderilen alanları uygular (auth ve assertions hariç).

        name, method, url, body_type, headers, query_params: None gelirse değişmez.
        description, body: gönderildiyse None dahil yazılır (boşaltma).
        Body tipi ve içeriği birlikte geçerli olmalı (biri eski, biri yeni olabilir).
        """
        check_json_body(changes.get("body_type", self.body_type), changes.get("body", self.body))
        for attr in ("name", "method", "url", "body_type", "headers", "query_params"):
            if changes.get(attr) is not None:
                setattr(self, attr, changes[attr])
        for attr in ("description", "body"):
            if attr in changes:
                setattr(self, attr, changes[attr])
