"""Celery uygulaması.

Worker:  celery -A app.worker.celery_app worker --loglevel=info
Beat:    celery -A app.worker.celery_app beat --loglevel=info
(Windows'ta worker için --pool=solo ekleyin.)
"""

from celery import Celery

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()

celery_app = Celery(
    "api_test_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Istanbul",
    enable_utc=True,
    task_track_started=True,
    result_expires=60 * 60 * 24,
    # Kuyruklar: test çalıştırmaları ayrı kuyrukta, ileride ayrı worker'a verilebilir
    task_routes={"app.worker.tasks.run_*": {"queue": "test_runs"}},
    task_default_queue="default",
    # Zamanlanmış görevler (ATOP-42'de veritabanından okunacak şekilde genişletilecek)
    beat_schedule={
        "heartbeat-every-5-minutes": {
            "task": "app.worker.tasks.heartbeat",
            "schedule": 300.0,
        },
    },
)
