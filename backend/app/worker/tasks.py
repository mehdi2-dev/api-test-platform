"""Celery görevleri (ATOP-41, ATOP-42).

- run_collection_task:      kuyruktaki bir koleksiyon çalıştırmasını yürütür
- dispatch_due_schedules:   Beat her dakika çağırır; zamanı gelen planları kuyruğa atar
"""

import logging
from datetime import UTC, datetime

from app.adapters.outbound.persistence.session import SessionLocal
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.run_collection_task")
def run_collection_task(
    collection_run_id: int, environment_id: int | None, confirm_production: bool
) -> str | None:
    from app.composition import execute_collection_run

    with SessionLocal() as db:
        collection_run = execute_collection_run(
            db, collection_run_id, environment_id, confirm_production
        )
        if collection_run is None:
            return None
        logger.info(
            "Koleksiyon çalıştırması %s bitti: %s", collection_run_id, collection_run.status
        )
        return collection_run.status.value if collection_run.status else None


@celery_app.task(name="app.worker.tasks.dispatch_due_schedules")
def dispatch_due_schedules() -> list[int]:
    from app.composition import celery_enqueue, dispatch_due

    with SessionLocal() as db:
        created = dispatch_due(db, datetime.now(UTC), celery_enqueue)
    if created:
        logger.info("Zamanlanmış çalıştırmalar kuyruğa atıldı: %s", created)
    return created


@celery_app.task(name="app.worker.tasks.heartbeat")
def heartbeat() -> str:
    """Beat'in ve worker'ın çalıştığını loglarda görmek için."""
    now = datetime.now(UTC).isoformat()
    logger.info("Heartbeat: %s", now)
    return now


@celery_app.task(name="app.worker.tasks.add")
def add(x: int, y: int) -> int:
    """Kuyruğun çalıştığını denemek için basit görev."""
    return x + y
