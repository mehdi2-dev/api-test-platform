"""Zamanlamalar: koleksiyonları cron ile düzenli çalıştırma (ATOP-42, ATOP-43).

Yetkiler:
- Herkes (giriş yapmış): planları ve sonraki çalışma zamanlarını görür
- Admin ve Tester: plan oluşturur, değiştirir, aktif/pasif yapar, siler, hemen çalıştırır
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.collections import Enqueuer, run_summary_fields
from app.api.deps import CurrentUser, DbSession, require_roles
from app.api.environments import get_environment_or_404
from app.core.config import settings
from app.models.collection import Collection, CollectionRun, RunState, RunTrigger, Schedule
from app.models.environment import Environment
from app.models.user import Role, User
from app.schemas.collection import CollectionRunSummary
from app.schemas.schedule import CronPreview, ScheduleCreate, ScheduleRead, ScheduleUpdate
from app.services import cron
from app.services.collection_runner import MUTATING_METHODS, finish_with_error, new_run
from app.services.scheduler import QUEUE_ERROR, compute_next

router = APIRouter(
    prefix="/schedules",
    tags=["Zamanlamalar"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Editor = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
NOT_FOUND = {404: {"description": "Plan bulunamadı"}}
FORBIDDEN = {403: {"description": "Sadece Admin ve Tester"}}


def _get_or_404(db: DbSession, schedule_id: int) -> Schedule:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plan bulunamadı")
    return schedule


def _to_read(db: DbSession, schedule: Schedule) -> ScheduleRead:
    last = db.get(CollectionRun, schedule.last_run_id) if schedule.last_run_id else None
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


def _check_production(
    collection: Collection, environment: Environment | None, confirm: bool
) -> None:
    """Production'da veri değiştiren adımları içeren plan açık onay ister (ATOP-30)."""
    if environment is None or not environment.is_production or confirm:
        return
    risky = [
        f"{item.api.method.value} {item.api.name}"
        for item in collection.items
        if item.enabled and item.api and item.api.method in MUTATING_METHODS
    ]
    if risky:
        raise HTTPException(
            422,
            detail=(
                f"'{environment.name}' Production ortamı ve koleksiyonda veri değiştiren "
                f"adımlar var ({', '.join(risky)}). Planlamak için Production onayını işaretleyin."
            ),
        )


def _refresh_next(schedule: Schedule) -> None:
    schedule.next_run_at = compute_next(schedule.cron) if schedule.enabled else None


@router.get(
    "/preview",
    response_model=CronPreview,
    summary="Cron ifadesinin sonraki çalışma zamanları",
    responses={422: {"description": "Geçersiz cron ifadesi"}},
)
def preview(
    _: CurrentUser,
    expression: Annotated[str, Query(alias="cron", description="ör. 0 9 * * 1-5")],
    count: Annotated[int, Query(ge=1, le=20)] = 5,
) -> CronPreview:
    try:
        parsed = cron.parse(expression)
        times = cron.next_runs(parsed, datetime.now(UTC), count, settings.timezone)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return CronPreview(cron=parsed.text, timezone=settings.timezone, next_runs=times)


@router.get("", response_model=list[ScheduleRead], summary="Planları listele")
def list_schedules(_: CurrentUser, db: DbSession) -> list[ScheduleRead]:
    query = select(Schedule).order_by(Schedule.enabled.desc(), Schedule.next_run_at, Schedule.id)
    return [_to_read(db, schedule) for schedule in db.scalars(query)]


@router.post(
    "",
    response_model=ScheduleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni plan",
    responses={**FORBIDDEN, 404: {"description": "Koleksiyon veya ortam bulunamadı"}},
)
def create_schedule(body: ScheduleCreate, user: Editor, db: DbSession) -> ScheduleRead:
    collection = db.get(Collection, body.collection_id)
    if collection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Koleksiyon bulunamadı")
    environment = get_environment_or_404(db, body.environment_id) if body.environment_id else None
    _check_production(collection, environment, body.confirm_production)

    schedule = Schedule(
        collection_id=collection.id,
        cron=body.cron,
        environment_id=body.environment_id,
        enabled=body.enabled,
        confirm_production=body.confirm_production,
        created_by_id=user.id,
    )
    _refresh_next(schedule)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _to_read(db, schedule)


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleRead,
    summary="Planı güncelle (cron, ortam, aktif/pasif)",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def update_schedule(
    schedule_id: int, body: ScheduleUpdate, _: Editor, db: DbSession
) -> ScheduleRead:
    schedule = _get_or_404(db, schedule_id)
    if body.cron is not None:
        schedule.cron = body.cron
    if "environment_id" in body.model_fields_set:
        if body.environment_id is not None:
            get_environment_or_404(db, body.environment_id)
        schedule.environment_id = body.environment_id
    if body.enabled is not None:
        schedule.enabled = body.enabled
    if body.confirm_production is not None:
        schedule.confirm_production = body.confirm_production

    environment = db.get(Environment, schedule.environment_id) if schedule.environment_id else None
    _check_production(schedule.collection, environment, schedule.confirm_production)
    _refresh_next(schedule)
    db.commit()
    db.refresh(schedule)
    return _to_read(db, schedule)


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Planı sil (geçmiş çalıştırmalar silinmez)",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_schedule(schedule_id: int, _: Editor, db: DbSession) -> None:
    db.delete(_get_or_404(db, schedule_id))
    db.commit()


@router.post(
    "/{schedule_id}/run-now",
    response_model=CollectionRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Planı beklemeden şimdi çalıştır",
    responses={**NOT_FOUND, **FORBIDDEN, 503: {"description": "Kuyruğa eklenemedi"}},
)
def run_now(
    schedule_id: int, user: Editor, db: DbSession, enqueue: Enqueuer
) -> CollectionRunSummary:
    schedule = _get_or_404(db, schedule_id)
    collection = schedule.collection
    if collection is None or not any(item.enabled for item in collection.items):
        raise HTTPException(422, detail="Koleksiyonda çalıştırılacak etkin adım yok")

    collection_run = new_run(
        collection,
        RunState.QUEUED,
        trigger=RunTrigger.SCHEDULE,
        user_id=user.id,
        environment_name=schedule.environment.name if schedule.environment else None,
        schedule_id=schedule.id,
    )
    db.add(collection_run)
    db.flush()
    schedule.last_run_at = datetime.now(UTC)
    schedule.last_run_id = collection_run.id
    db.commit()
    db.refresh(collection_run)

    try:
        enqueue(collection_run.id, schedule.environment_id, schedule.confirm_production)
    except Exception as exc:
        finish_with_error(db, collection_run, QUEUE_ERROR)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=QUEUE_ERROR) from exc

    db.refresh(collection_run)
    return CollectionRunSummary(**run_summary_fields(collection_run))
