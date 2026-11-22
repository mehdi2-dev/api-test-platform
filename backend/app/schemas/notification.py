"""Bildirim kanalı şemaları (ATOP-48)."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ChannelType = Literal["slack", "teams", "webhook", "email"]
NotifyOn = Literal["failure", "always"]

EMAIL = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")


def check_target(channel_type: str, target: str) -> str:
    target = target.strip()
    if channel_type == "email":
        addresses = [item.strip() for item in target.split(",") if item.strip()]
        if not addresses or not all(EMAIL.match(item) for item in addresses):
            raise ValueError("Geçerli e-posta adres(ler)i girin (virgülle ayırabilirsiniz)")
        return ", ".join(addresses)
    if not target.startswith(("http://", "https://")):
        raise ValueError("Webhook adresi http:// veya https:// ile başlamalı")
    return target


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
