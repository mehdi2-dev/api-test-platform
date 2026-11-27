"""Kompozisyon kökü: use case'leri gerçek adaptörlerle kuran fonksiyonlar.

HTTP router'ları (FastAPI bağımlılıklarıyla), Celery görevleri ve CLI, use case'leri
buradan alır. Hangi porta hangi adaptörün takılacağına karar verilen yer burasıdır.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.adapters.outbound.http.sender import HttpxApiSender
from app.adapters.outbound.notifications.run_notifier import SafeRunNotifier
from app.adapters.outbound.persistence.collections import (
    SqlAlchemyCollectionRepository,
    SqlAlchemyCollectionRunRepository,
)
from app.adapters.outbound.persistence.environments import SqlAlchemyEnvironmentRepository
from app.adapters.outbound.persistence.schedules import SqlAlchemyScheduleRepository
from app.adapters.outbound.persistence.test_runs import SqlAlchemyApiTestRunRepository
from app.adapters.outbound.queue import CallableRunQueue
from app.adapters.outbound.security.cipher import FernetCipher
from app.application.use_cases.collection_runs import (  # noqa: F401
    ExecuteQueuedRun,
    PrepareCollectionRun,
    RunCollection,
    RunContext,
)
from app.application.use_cases.collections import QUEUE_ERROR  # noqa: F401
from app.application.use_cases.schedules import DispatchDueSchedules
from app.core.config import settings
from app.domain.api_definitions import MUTATING_METHODS  # noqa: F401
from app.domain.collections import (  # noqa: F401
    Collection,
    CollectionRun,
    RunState,
    RunTrigger,
    extract_value,
)
from app.domain.errors import ProductionConfirmationRequired  # noqa: F401
from app.domain.schedules import next_run

# (collection_run_id, environment_id, confirm_production) -> kuyruğa at
Enqueue = Callable[[int, int | None, bool], None]


def preparer(db: Session) -> PrepareCollectionRun:
    return PrepareCollectionRun(SqlAlchemyEnvironmentRepository(db), FernetCipher())


def runner(db: Session, transport: httpx.BaseTransport | None) -> RunCollection:
    return RunCollection(
        HttpxApiSender(transport),
        SqlAlchemyApiTestRunRepository(db),
        SqlAlchemyCollectionRunRepository(db),
        FernetCipher(),
        SafeRunNotifier(db, transport),
    )


def build_context(
    db: Session, collection: Collection, environment_id: int | None, confirm_production: bool
) -> RunContext:
    return preparer(db)(collection, environment_id, confirm_production)


def new_run(
    collection: Collection,
    state: RunState,
    trigger: RunTrigger = RunTrigger.MANUAL,
    user_id: int | None = None,
    environment_name: str | None = None,
    schedule_id: int | None = None,
) -> CollectionRun:
    return CollectionRun.new(collection, state, trigger, user_id, environment_name, schedule_id)


def finish_with_error(db: Session, collection_run: CollectionRun, message: str) -> CollectionRun:
    collection_run.fail(message)
    SqlAlchemyCollectionRunRepository(db).save(collection_run)
    return collection_run


def run_collection(
    db: Session,
    collection: Collection,
    context: RunContext,
    user_id: int | None,
    transport: httpx.BaseTransport | None = None,
    collection_run: CollectionRun | None = None,
) -> CollectionRun:
    return runner(db, transport)(collection, context, user_id, collection_run=collection_run)


def execute_collection_run(
    db: Session,
    collection_run_id: int,
    environment_id: int | None,
    confirm_production: bool,
    transport: httpx.BaseTransport | None = None,
) -> CollectionRun | None:
    """Kuyruktaki bir çalıştırmayı yürütür (Celery worker bunu çağırır)."""
    return ExecuteQueuedRun(
        SqlAlchemyCollectionRepository(db),
        SqlAlchemyCollectionRunRepository(db),
        preparer(db),
        runner(db, transport),
        SafeRunNotifier(db, transport),
    )(collection_run_id, environment_id, confirm_production)


# --- Zamanlama ---


def celery_enqueue(collection_run_id: int, environment_id: int | None, confirm: bool) -> None:
    """Gerçek kuyruk: Celery worker'a gönder."""
    from app.worker.tasks import run_collection_task  # celery'yi sadece gerekince yükle

    run_collection_task.delay(collection_run_id, environment_id, confirm)


def compute_next(cron_text: str, after: datetime | None = None) -> datetime:
    return next_run(cron_text, after or datetime.now(UTC), settings.timezone)


def dispatch_due(db: Session, now: datetime, enqueue: Enqueue) -> list[int]:
    """Zamanı gelen planları kuyruğa atar (Celery Beat her dakika çağırır)."""
    return DispatchDueSchedules(
        SqlAlchemyScheduleRepository(db),
        SqlAlchemyCollectionRunRepository(db),
        CallableRunQueue(enqueue),
        settings.timezone,
    )(now)
