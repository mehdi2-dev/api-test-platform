"""Giren adaptör: zamanlamalar; koleksiyonları cron ile düzenli çalıştırma.

Yetkiler:
- Herkes (giriş yapmış): planları ve sonraki çalışma zamanlarını görür
- Admin ve Tester: plan oluşturur, değiştirir, aktif/pasif yapar, siler, hemen çalıştırır
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.adapters.inbound.http.collections import Enqueuer, run_summary_fields
from app.adapters.inbound.http.dependencies import (
    ClockDep,
    CollectionRuns,
    Collections,
    CurrentUser,
    Environments,
    Schedules,
    require_roles,
)
from app.adapters.inbound.http.schemas.collection import CollectionRunSummary
from app.adapters.inbound.http.schemas.schedule import (
    CronPreview,
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
)
from app.adapters.outbound.queue import CallableRunQueue
from app.application.use_cases.environments import UNCHANGED
from app.application.use_cases.schedules import (
    CreateSchedule,
    DeleteSchedule,
    ListSchedules,
    PreviewCron,
    RunScheduleNow,
    ScheduleOverview,
    UpdateSchedule,
)
from app.core.config import settings
from app.domain.users import Role, User

router = APIRouter(
    prefix="/schedules",
    tags=["Zamanlamalar"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Editor = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
NOT_FOUND = {404: {"description": "Plan bulunamadı"}}
FORBIDDEN = {403: {"description": "Sadece Admin ve Tester"}}


def get_preview(clock: ClockDep) -> PreviewCron:
    return PreviewCron(clock, settings.timezone)


def get_list(schedules: Schedules, runs: CollectionRuns) -> ListSchedules:
    return ListSchedules(schedules, runs)


def get_create(
    schedules: Schedules, collections: Collections, environments: Environments, clock: ClockDep
) -> CreateSchedule:
    return CreateSchedule(schedules, collections, environments, clock, settings.timezone)


def get_update(schedules: Schedules, environments: Environments, clock: ClockDep) -> UpdateSchedule:
    return UpdateSchedule(schedules, environments, clock, settings.timezone)


def get_delete(schedules: Schedules) -> DeleteSchedule:
    return DeleteSchedule(schedules)


def get_run_now(
    schedules: Schedules, runs: CollectionRuns, enqueue: Enqueuer, clock: ClockDep
) -> RunScheduleNow:
    return RunScheduleNow(schedules, runs, CallableRunQueue(enqueue), clock)


Listing = Annotated[ListSchedules, Depends(get_list)]


def _to_read(row: ScheduleOverview) -> ScheduleRead:
    schedule, last = row.schedule, row.last_run
    environment = schedule.environment
    return ScheduleRead(
        id=schedule.id,
        collection_id=schedule.collection_id,
        collection_name=schedule.collection.name if schedule.collection else "(silinmiş)",
        cron=schedule.cron,
        environment_id=schedule.environment_id,
        environment_name=environment.name if environment else None,
        is_production=bool(environment and environment.is_production),
        enabled=schedule.enabled,
        confirm_production=schedule.confirm_production,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        last_run_id=schedule.last_run_id,
        last_run_status=last.status if last else None,
        last_run_state=last.state if last else None,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


@router.get(
    "/preview",
    response_model=CronPreview,
    summary="Cron ifadesinin sonraki çalışma zamanları",
    responses={422: {"description": "Geçersiz cron ifadesi"}},
)
def preview(
    _: CurrentUser,
    use_case: Annotated[PreviewCron, Depends(get_preview)],
    expression: Annotated[str, Query(alias="cron", description="ör. 0 9 * * 1-5")],
    count: Annotated[int, Query(ge=1, le=20)] = 5,
) -> CronPreview:
    result = use_case(expression, count)
    return CronPreview(cron=result.cron, timezone=result.timezone, next_runs=result.next_runs)


@router.get("", response_model=list[ScheduleRead], summary="Planları listele")
def list_schedules(_: CurrentUser, use_case: Listing) -> list[ScheduleRead]:
    return [_to_read(row) for row in use_case()]


@router.post(
    "",
    response_model=ScheduleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni plan",
    responses={**FORBIDDEN, 404: {"description": "Koleksiyon veya ortam bulunamadı"}},
)
def create_schedule(
    body: ScheduleCreate,
    user: Editor,
    use_case: Annotated[CreateSchedule, Depends(get_create)],
    listing: Listing,
) -> ScheduleRead:
    schedule = use_case(
        created_by=user,
        collection_id=body.collection_id,
        cron_text=body.cron,
        environment_id=body.environment_id,
        enabled=body.enabled,
        confirm_production=body.confirm_production,
    )
    return _to_read(listing.overview(schedule))


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleRead,
    summary="Planı güncelle (cron, ortam, aktif/pasif)",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    _: Editor,
    use_case: Annotated[UpdateSchedule, Depends(get_update)],
    listing: Listing,
) -> ScheduleRead:
    schedule = use_case(
        schedule_id,
        cron_text=body.cron,
        environment_id=(
            body.environment_id if "environment_id" in body.model_fields_set else UNCHANGED
        ),
        enabled=body.enabled,
        confirm_production=body.confirm_production,
    )
    return _to_read(listing.overview(schedule))


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Planı sil (geçmiş çalıştırmalar silinmez)",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_schedule(
    schedule_id: int,
    _: Editor,
    use_case: Annotated[DeleteSchedule, Depends(get_delete)],
) -> None:
    use_case(schedule_id)


@router.post(
    "/{schedule_id}/run-now",
    response_model=CollectionRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Planı beklemeden şimdi çalıştır",
    responses={**NOT_FOUND, **FORBIDDEN, 503: {"description": "Kuyruğa eklenemedi"}},
)
def run_now(
    schedule_id: int,
    user: Editor,
    use_case: Annotated[RunScheduleNow, Depends(get_run_now)],
) -> CollectionRunSummary:
    return CollectionRunSummary(**run_summary_fields(use_case(schedule_id, user=user)))
