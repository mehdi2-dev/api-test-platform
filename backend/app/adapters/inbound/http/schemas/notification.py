"""Bildirim kanalı şemaları (ATOP-48)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.errors import InvalidInput
from app.domain.notifications import check_target as _check_target

ChannelType = Literal["slack", "teams", "webhook", "email"]
NotifyOn = Literal["failure", "always"]


def check_target(channel_type: str, target: str) -> str:
    """Kural domain'dedir; pydantic doğrulaması için ValueError'a çevrilir."""
    try:
        return _check_target(channel_type, target)
    except InvalidInput as exc:
        raise ValueError(exc.message) from exc


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: ChannelType
    target: str = Field(
        min_length=1, max_length=2000, description="Webhook adresi ya da e-posta adres(ler)i"
    )
    enabled: bool = True
    notify_on: NotifyOn = "failure"

    @model_validator(mode="after")
    def check(self) -> "ChannelCreate":
        self.name = self.name.strip()
        self.target = check_target(self.type, self.target)
        return self


class ChannelUpdate(BaseModel):
    """target gönderilmezse kayıtlı adres korunur."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    target: str | None = Field(default=None, min_length=1, max_length=2000)
    enabled: bool | None = None
    notify_on: NotifyOn | None = None


class ChannelRead(BaseModel):
    id: int
    name: str
    type: ChannelType
    target_preview: str = Field(description="Webhook adresinin gizlenmiş hali")
    enabled: bool
    notify_on: NotifyOn
    last_sent_at: datetime | None
    last_status: str | None
    last_error: str | None
    created_at: datetime


class ChannelTestResult(BaseModel):
    ok: bool
    error: str | None = None
