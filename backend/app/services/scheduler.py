"""Geçiş dönemi (ATOP-63): zamanı gelen planları kuyruğa atma artık bir use case.

Asıl akış app.application.use_cases.schedules.DispatchDueSchedules içindedir. Celery Beat
her dakika `dispatch_due_schedules` görevini tetikler; görev buradaki dispatch_due'yu çağırır.
Kuyruğa atma işi `enqueue` parametresiyle verilir; testlerde Celery olmadan çalışır.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.adapters.outbound.persistence.collections import SqlAlchemyCollectionRunRepository
from app.adapters.outbound.persistence.schedules import SqlAlchemyScheduleRepository
from app.adapters.outbound.queue import CallableRunQueue
from app.application.use_cases.collections import QUEUE_ERROR  # noqa: F401
from app.application.use_cases.schedules import DispatchDueSchedules
from app.core.config import settings
from app.domain.schedules import next_run

# (collection_run_id, environment_id, confirm_production) -> kuyruğa at
Enqueue = Callable[[int, int | None, bool], None]


def celery_enqueue(collection_run_id: int, environment_id: int | None, confirm: bool) -> None:
    """Gerçek kuyruk: Celery worker'a gönder."""
    from app.worker.tasks import run_collection_task  # celery'yi sadece gerekince yükle

    run_collection_task.delay(collection_run_id, environment_id, confirm)


def compute_next(cron_text: str, after: datetime | None = None) -> datetime:
    return next_run(cron_text, after or datetime.now(UTC), settings.timezone)


def dispatch_due(db: Session, now: datetime, enqueue: Enqueue) -> list[int]:
    """Zamanı gelen planları çalıştırır; oluşturulan çalıştırma id'lerini döndürür."""
    return DispatchDueSchedules(
        SqlAlchemyScheduleRepository(db),
        SqlAlchemyCollectionRunRepository(db),
        CallableRunQueue(enqueue),
        settings.timezone,
    )(now)
