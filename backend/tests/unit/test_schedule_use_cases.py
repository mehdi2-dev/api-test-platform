"""Zamanlama planları ve zamanı gelen planları dağıtma; sabit saat ve bellek içi depolarla.

Celery, Redis veya veritabanı yok: kuyruk bir liste, saat sabit.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.outbound.queue import CallableRunQueue
from app.application.errors import QueueUnavailable
from app.application.use_cases.collections import QUEUE_ERROR
from app.application.use_cases.schedules import (
    CreateSchedule,
    DispatchDueSchedules,
    PreviewCron,
    RunScheduleNow,
    UpdateSchedule,
)
from app.domain.api_definitions import ApiDefinition, HttpMethod
from app.domain.collections import Collection, StepInput
from app.domain.environments import Environment
from app.domain.errors import InvalidInput, NotFound
from app.domain.schedules import Schedule
from app.domain.testing.runs import RunStatus
from app.domain.users import Role, User
from tests.fakes import (
    FixedClock,
    InMemoryCollectionRepository,
    InMemoryCollectionRunRepository,
    InMemoryEnvironmentRepository,
    InMemoryScheduleRepository,
)

TZ = "Europe/Istanbul"
NOW = datetime(2030, 1, 7, 6, 30, tzinfo=UTC)  # pazartesi 09:30 İstanbul
TESTER = User(email="t@apitest.com", full_name="T", hashed_password="x", role=Role.TESTER, id=7)


@pytest.fixture
def world():
    collections = InMemoryCollectionRepository()
    collection = Collection(name="Sipariş akışı")
    collection.replace_items([StepInput(1)])
    collection.items[0].api = ApiDefinition(
        id=1, name="Sipariş oluştur", url="https://x", method=HttpMethod.POST
    )
    collections.save(collection)

    environments = InMemoryEnvironmentRepository()
    environments.save(Environment(name="Prod", is_production=True))
    runs = InMemoryCollectionRunRepository()
    schedules = InMemoryScheduleRepository(runs, collections, environments)
    return collections, environments, runs, schedules


def create(world, **changes) -> Schedule:
    collections, environments, _, schedules = world
    data = {
        "created_by": TESTER,
        "collection_id": 1,
        "cron_text": "0 9 * * 1-5",
        "environment_id": None,
        "enabled": True,
        "confirm_production": False,
        **changes,
    }
    return CreateSchedule(schedules, collections, environments, FixedClock(NOW), TZ)(**data)


def test_next_run_is_computed_in_local_time(world) -> None:
    schedule = create(world)
    # pazartesi 09:30'u geçti; sonraki hafta içi 09:00 = salı 06:00 UTC
    assert schedule.next_run_at == datetime(2030, 1, 8, 6, 0, tzinfo=UTC)


def test_disabled_schedule_has_no_next_run(world) -> None:
    assert create(world, enabled=False).next_run_at is None


def test_production_needs_confirmation_when_planning(world) -> None:
    with pytest.raises(InvalidInput, match="Production onayını işaretleyin"):
        create(world, environment_id=1)
    assert create(world, environment_id=1, confirm_production=True).confirm_production


def test_unknown_collection_or_environment(world) -> None:
    with pytest.raises(NotFound, match="Koleksiyon"):
        create(world, collection_id=99)
    with pytest.raises(NotFound, match="Ortam"):
        create(world, environment_id=99)


def test_update_can_clear_environment_and_disable(world) -> None:
    _, environments, _, schedules = world
    schedule = create(world, environment_id=1, confirm_production=True)

    UpdateSchedule(schedules, environments, FixedClock(NOW), TZ)(
        schedule.id, environment_id=None, enabled=False
    )

    assert (schedule.environment_id, schedule.enabled, schedule.next_run_at) == (None, False, None)


def test_preview_rejects_invalid_cron() -> None:
    preview = PreviewCron(FixedClock(NOW), TZ)
    assert len(preview("*/15 * * * *", 3).next_runs) == 3
    with pytest.raises(InvalidInput):
        preview("her gün", 3)


def test_dispatch_queues_due_schedules_and_moves_next_run(world) -> None:
    _, _, runs, schedules = world
    due = create(world)
    due.next_run_at = NOW - timedelta(minutes=1)
    create(world, enabled=False).next_run_at = NOW - timedelta(minutes=1)
    queued: list[tuple] = []

    created = DispatchDueSchedules(
        schedules, runs, CallableRunQueue(lambda *a: queued.append(a)), TZ
    )(NOW)

    assert queued == [(created[0], None, False)]
    run = runs.get(created[0])
    assert (run.state, run.trigger, run.schedule_id, run.triggered_by_id) == (
        "queued",
        "schedule",
        due.id,
        7,
    )
    assert due.last_run_id == run.id and due.next_run_at > NOW


def test_dispatch_marks_run_failed_when_queue_is_down(world) -> None:
    _, _, runs, schedules = world
    create(world).next_run_at = NOW

    def broken(*_):
        raise ConnectionError("Redis yok")

    [run_id] = DispatchDueSchedules(schedules, runs, CallableRunQueue(broken), TZ)(NOW)

    assert (runs.get(run_id).status, runs.get(run_id).error) == (RunStatus.ERROR, QUEUE_ERROR)


def test_run_now_records_last_run_and_reports_queue_errors(world) -> None:
    _, _, runs, schedules = world
    schedule = create(world)
    queued: list[tuple] = []

    run = RunScheduleNow(
        schedules, runs, CallableRunQueue(lambda *a: queued.append(a)), FixedClock(NOW)
    )(schedule.id, user=TESTER)

    assert (schedule.last_run_id, schedule.last_run_at) == (run.id, NOW)
    assert queued == [(run.id, None, False)]

    def broken(*_):
        raise ConnectionError("Redis yok")

    with pytest.raises(QueueUnavailable):
        RunScheduleNow(schedules, runs, CallableRunQueue(broken), FixedClock(NOW))(
            schedule.id, user=TESTER
        )
