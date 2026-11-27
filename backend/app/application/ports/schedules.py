"""Zamanlama planları ve saat için portlar."""

from datetime import datetime
from typing import Protocol

from app.domain.collections import CollectionRun
from app.domain.schedules import Schedule


class ScheduleRepository(Protocol):
    def get(self, schedule_id: int) -> Schedule | None: ...

    def list_all(self) -> list[Schedule]:
        """Önce etkin olanlar, sonra sonraki çalışma zamanına göre."""
        ...

    def save(self, schedule: Schedule) -> None: ...

    def delete(self, schedule: Schedule) -> None: ...

    def due(self, now: datetime) -> list[Schedule]:
        """Zamanı gelmiş etkin planlar. commit'e kadar kilitlenir ki aynı anda çalışan iki
        zamanlayıcı aynı planı iki kez almasın."""
        ...

    def stage_run(self, run: CollectionRun) -> None:
        """Çalıştırmayı kaydeder ve id verir ama commit etmez (kilitler korunur)."""
        ...

    def commit(self) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Şu an (UTC)."""
        ...
