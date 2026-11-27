"""Use case'ler: zamanlama planları ve zamanı gelen planları kuyruğa atma."""

import logging
from dataclasses import dataclass
from datetime import datetime

from app.application.errors import QueueUnavailable
from app.application.ports.collections import (
    CollectionRepository,
    CollectionRunRepository,
    RunQueue,
)
from app.application.ports.environments import EnvironmentRepository
from app.application.ports.schedules import Clock, ScheduleRepository
from app.application.use_cases.collections import NO_ENABLED_STEPS, QUEUE_ERROR
from app.application.use_cases.environments import UNCHANGED, GetEnvironment, _Unchanged
from app.domain import cron
from app.domain.collections import CollectionRun, RunState, RunTrigger
from app.domain.errors import InvalidInput, NotFound
from app.domain.schedules import Schedule, next_run
from app.domain.users import User

logger = logging.getLogger(__name__)


@dataclass
class CronPreviewResult:
    cron: str
    timezone: str
    next_runs: list[datetime]


class PreviewCron:
    """Cron ifadesinin sonraki çalışma zamanları (plan kaydetmeden önce göstermek için)."""

    def __init__(self, clock: Clock, timezone: str) -> None:
        self._clock = clock
        self._timezone = timezone

    def __call__(self, expression: str, count: int) -> CronPreviewResult:
        try:
            parsed = cron.parse(expression)
            times = cron.next_runs(parsed, self._clock.now(), count, self._timezone)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        return CronPreviewResult(parsed.text, self._timezone, times)


@dataclass
class ScheduleOverview:
    schedule: Schedule
    last_run: CollectionRun | None


class ListSchedules:
    def __init__(self, schedules: ScheduleRepository, runs: CollectionRunRepository) -> None:
        self._schedules = schedules
        self._runs = runs

    def overview(self, schedule: Schedule) -> ScheduleOverview:
        last = self._runs.get(schedule.last_run_id) if schedule.last_run_id else None
        return ScheduleOverview(schedule, last)

    def __call__(self) -> list[ScheduleOverview]:
        return [self.overview(schedule) for schedule in self._schedules.list_all()]


class GetSchedule:
    def __init__(self, schedules: ScheduleRepository) -> None:
        self._schedules = schedules

    def __call__(self, schedule_id: int) -> Schedule:
        schedule = self._schedules.get(schedule_id)
        if schedule is None:
            raise NotFound("Plan bulunamadı")
        return schedule


class CreateSchedule:
    def __init__(
        self,
        schedules: ScheduleRepository,
        collections: CollectionRepository,
        environments: EnvironmentRepository,
        clock: Clock,
        timezone: str,
    ) -> None:
        self._schedules = schedules
        self._collections = collections
        self._environments = environments
        self._clock = clock
        self._timezone = timezone

    def __call__(
        self,
        *,
        created_by: User,
        collection_id: int,
        cron_text: str,
        environment_id: int | None,
        enabled: bool,
        confirm_production: bool,
    ) -> Schedule:
        collection = self._collections.get(collection_id)
        if collection is None:
            raise NotFound("Koleksiyon bulunamadı")
        environment = GetEnvironment(self._environments)(environment_id) if environment_id else None
        Schedule.ensure_production_confirmed(collection, environment, confirm_production)

        schedule = Schedule(
            collection_id=collection.id,
            cron=cron_text,
            environment_id=environment_id,
            enabled=enabled,
            confirm_production=confirm_production,
            created_by_id=created_by.id,
        )
        schedule.schedule_next(self._clock.now(), self._timezone)
        self._schedules.save(schedule)
        return schedule


class UpdateSchedule:
    def __init__(
        self,
        schedules: ScheduleRepository,
        environments: EnvironmentRepository,
        clock: Clock,
        timezone: str,
    ) -> None:
        self._schedules = schedules
        self._environments = environments
        self._clock = clock
        self._timezone = timezone

    def __call__(
        self,
        schedule_id: int,
        *,
        cron_text: str | None = None,
        environment_id: int | None | _Unchanged = UNCHANGED,
        enabled: bool | None = None,
        confirm_production: bool | None = None,
    ) -> Schedule:
        schedule = GetSchedule(self._schedules)(schedule_id)
        if cron_text is not None:
            schedule.cron = cron_text
        if not isinstance(environment_id, _Unchanged):
            if environment_id is not None:
                GetEnvironment(self._environments)(environment_id)
            schedule.environment_id = environment_id
        if enabled is not None:
            schedule.enabled = enabled
        if confirm_production is not None:
            schedule.confirm_production = confirm_production

        environment = (
            self._environments.get(schedule.environment_id) if schedule.environment_id else None
        )
        Schedule.ensure_production_confirmed(
            schedule.collection, environment, schedule.confirm_production
        )
        schedule.schedule_next(self._clock.now(), self._timezone)
        self._schedules.save(schedule)
        return schedule


class DeleteSchedule:
    """Planı siler; geçmiş çalıştırmalar silinmez."""

    def __init__(self, schedules: ScheduleRepository) -> None:
        self._schedules = schedules

    def __call__(self, schedule_id: int) -> None:
        self._schedules.delete(GetSchedule(self._schedules)(schedule_id))


def _queued_run(schedule: Schedule, user_id: int | None) -> CollectionRun:
    environment = schedule.environment
    return CollectionRun.new(
        schedule.collection,
        RunState.QUEUED,
        trigger=RunTrigger.SCHEDULE,
        user_id=user_id,
        environment_name=environment.name if environment else None,
        schedule_id=schedule.id,
    )


class RunScheduleNow:
    """Planı beklemeden şimdi kuyruğa atar."""

    def __init__(
        self,
        schedules: ScheduleRepository,
        runs: CollectionRunRepository,
        queue: RunQueue,
        clock: Clock,
    ) -> None:
        self._schedules = schedules
        self._runs = runs
        self._queue = queue
        self._clock = clock

    def __call__(self, schedule_id: int, *, user: User) -> CollectionRun:
        schedule = GetSchedule(self._schedules)(schedule_id)
        collection = schedule.collection
        if collection is None or not collection.enabled_items:
            raise InvalidInput(NO_ENABLED_STEPS)

        run = _queued_run(schedule, user.id)
        self._runs.save(run)
        schedule.last_run_at = self._clock.now()
        schedule.last_run_id = run.id
        self._schedules.save(schedule)

        try:
            self._queue.enqueue(run.id, schedule.environment_id, schedule.confirm_production)
        except Exception as exc:
            run.fail(QUEUE_ERROR)
            self._runs.save(run)
            raise QueueUnavailable(QUEUE_ERROR) from exc
        return run


class DispatchDueSchedules:
    """Zamanı gelen planları çalıştırır; oluşturulan çalıştırma id'lerini döndürür.

    1. Zamanı gelmiş (next_run_at <= şimdi) etkin planları bul
    2. Her biri için "queued" bir koleksiyon çalıştırması oluştur
    3. next_run_at'i cron'a göre bir sonraki zamana ilerlet
    4. Önce kaydet ki worker kaydı bulabilsin, sonra kuyruğa at
    """

    def __init__(
        self,
        schedules: ScheduleRepository,
        runs: CollectionRunRepository,
        queue: RunQueue,
        timezone: str,
    ) -> None:
        self._schedules = schedules
        self._runs = runs
        self._queue = queue
        self._timezone = timezone

    def __call__(self, now: datetime) -> list[int]:
        to_enqueue: list[tuple[int, int | None, bool]] = []
        for schedule in self._schedules.due(now):
            schedule.last_run_at = now
            schedule.next_run_at = next_run(schedule.cron, now, self._timezone)
            collection = schedule.collection
            if collection is None or not collection.enabled_items:
                logger.info("Plan %s atlandı: koleksiyonda etkin adım yok", schedule.id)
                continue

            run = _queued_run(schedule, schedule.created_by_id)
            self._schedules.stage_run(run)
            schedule.last_run_id = run.id
            to_enqueue.append((run.id, schedule.environment_id, schedule.confirm_production))
        self._schedules.commit()

        for run_id, environment_id, confirm in to_enqueue:
            try:
                self._queue.enqueue(run_id, environment_id, confirm)
            except Exception:
                logger.exception("Zamanlanmış çalıştırma kuyruğa atılamadı: %s", run_id)
                run = self._runs.get(run_id)
                if run is not None:
                    run.fail(QUEUE_ERROR)
                    self._runs.save(run)
        return [run_id for run_id, _, _ in to_enqueue]
