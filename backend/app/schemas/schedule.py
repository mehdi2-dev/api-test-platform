"""Zamanlama (cron) şemaları (ATOP-42, ATOP-43)."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.domain import cron
from app.models.test_run import RunStatus


def _check_cron(value: str) -> str:
    return cron.validate(value, settings.timezone)


class ScheduleCreate(BaseModel):
    collection_id: int
    cron: str = Field(
        min_length=1,
        max_length=100,
        description="5 alanlı cron: dakika saat gün ay haftanın-günü (ör. 0 9 * * 1-5)",
    )
    environment_id: int | None = None
    enabled: bool = True
    confirm_production: bool = Field(
        default=False,
        description="Production ortamında veri değiştiren adımların çalışmasına izin ver",
    )

    @field_validator("cron")
    @classmethod
    def check_cron(cls, value: str) -> str:
        return _check_cron(value)


class ScheduleUpdate(BaseModel):
    """Gönderilen alanlar değişir. environment_id: null göndermek ortamı kaldırır."""

    cron: str | None = Field(default=None, min_length=1, max_length=100)
    environment_id: int | None = None
    enabled: bool | None = None
    confirm_production: bool | None = None

    @field_validator("cron")
    @classmethod
    def check_cron(cls, value: str | None) -> str | None:
        return None if value is None else _check_cron(value)


class ScheduleRead(BaseModel):
    id: int
    collection_id: int
    collection_name: str
    cron: str
    environment_id: int | None
    environment_name: str | None
    is_production: bool
    enabled: bool
    confirm_production: bool
    next_run_at: datetime | None = Field(description="Bir sonraki çalışma (UTC)")
    last_run_at: datetime | None
    last_run_id: int | None
    last_run_status: RunStatus | None = None
    last_run_state: str | None = None
    created_at: datetime
    updated_at: datetime


class CronPreview(BaseModel):
    cron: str
    timezone: str
    next_runs: list[datetime]
