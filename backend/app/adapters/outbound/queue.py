"""RunQueue portunun adaptörü.

Gerçekte Celery'ye gönderen fonksiyonu (app.services.scheduler.celery_enqueue) sarar;
testlerde Celery olmadan çalışan bir fonksiyon verilebilir.
"""

from collections.abc import Callable

Enqueue = Callable[[int, int | None, bool], None]


class CallableRunQueue:
    def __init__(self, enqueue: Enqueue) -> None:
        self._enqueue = enqueue

    def enqueue(self, run_id: int, environment_id: int | None, confirm_production: bool) -> None:
        self._enqueue(run_id, environment_id, confirm_production)
