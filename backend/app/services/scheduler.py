"""Zamanlanmış çalıştırmaları kuyruğa atma (ATOP-42).

Celery Beat her dakika `dispatch_due_schedules` görevini tetikler; o da bu modüldeki
dispatch_due() fonksiyonunu çağırır:

    1. Zamanı gelmiş (next_run_at <= şimdi) etkin planları bul
    2. Her biri için "queued" bir koleksiyon çalıştırması oluştur
    3. next_run_at'i cron'a göre bir sonraki zamana ilerlet
    4. Çalıştırmaları kuyruğa at (worker yürütür)

Kuyruğa atma işi `enqueue` parametresiyle verilir; testlerde Celery olmadan çalıştırılabilir.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.collection import CollectionRun, RunState, RunTrigger, Schedule
from app.services import cron
from app.services.collection_runner import finish_with_error, new_run

logger = logging.getLogger(__name__)

# (collection_run_id, environment_id, confirm_production) -> kuyruğa at
Enqueue = Callable[[int, int | None, bool], None]
QUEUE_ERROR = "Kuyruğa eklenemedi (Redis ve worker çalışıyor mu?)"


def celery_enqueue(collection_run_id: int, environment_id: int | None, confirm: bool) -> None:
    """Gerçek kuyruk: Celery worker'a gönder."""
    from app.worker.tasks import run_collection_task  # celery'yi sadece gerekince yükle

    run_collection_task.delay(collection_run_id, environment_id, confirm)


def compute_next(cron_text: str, after: datetime | None = None) -> datetime:
    return cron.next_after(cron.parse(cron_text), after or datetime.now(UTC), settings.timezone)


def dispatch_due(db: Session, now: datetime, enqueue: Enqueue) -> list[int]:
    """Zamanı gelen planları çalıştırır; oluşturulan çalıştırma id'lerini döndürür."""
    due = db.scalars(
        select(Schedule)
        .where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
        .order_by(Schedule.next_run_at)
        # Aynı anda iki beat çalışırsa aynı plan iki kez alınmasın (PostgreSQL)
        .with_for_update(skip_locked=True)
    ).all()

    to_enqueue: list[tuple[int, int | None, bool]] = []
    for schedule in due:
        collection = schedule.collection
        schedule.last_run_at = now
        schedule.next_run_at = compute_next(schedule.cron, now)
        if collection is None or not any(item.enabled for item in collection.items):
            logger.info("Plan %s atlandı: koleksiyonda etkin adım yok", schedule.id)
            continue

        collection_run = new_run(
            collection,
            RunState.QUEUED,
            trigger=RunTrigger.SCHEDULE,
            user_id=schedule.created_by_id,
            environment_name=schedule.environment.name if schedule.environment else None,
            schedule_id=schedule.id,
        )
        db.add(collection_run)
        db.flush()
        schedule.last_run_id = collection_run.id
        to_enqueue.append((collection_run.id, schedule.environment_id, schedule.confirm_production))

    # Önce kaydet ki worker kaydı bulabilsin, sonra kuyruğa at
    db.commit()
    for run_id, environment_id, confirm in to_enqueue:
        try:
            enqueue(run_id, environment_id, confirm)
        except Exception:
            logger.exception("Zamanlanmış çalıştırma kuyruğa atılamadı: %s", run_id)
            collection_run = db.get(CollectionRun, run_id)
            if collection_run is not None:
                finish_with_error(db, collection_run, QUEUE_ERROR)
    return [run_id for run_id, _, _ in to_enqueue]
