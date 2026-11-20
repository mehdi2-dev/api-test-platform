"""Celery görevleri. Test çalıştırma görevleri ATOP-41'de buraya eklenecek."""

import logging
from datetime import UTC, datetime

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


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
