"""Celery uygulaması.

Worker:  celery -A app.worker.celery_app worker --loglevel=info
Beat:    celery -A app.worker.celery_app beat --loglevel=info
(Windows'ta worker için --pool=solo ekleyin.)
"""

from celery import Celery
from celery.schedules import crontab

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
    # Worker çökerse görev kaybolmasın: bitince onayla
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Beat'in sabit görevleri. Kullanıcı planları veritabanında (schedules tablosu);
    # dispatch_due_schedules her dakika zamanı gelenleri kuyruğa atar (ATOP-42).
    beat_schedule={
        "dispatch-due-schedules-every-minute": {
            "task": "app.worker.tasks.dispatch_due_schedules",
            "schedule": crontab(),  # her dakikanın başında
        },
        "heartbeat-every-hour": {
            "task": "app.worker.tasks.heartbeat",
            "schedule": 3600.0,
        },
    },
)
