"""Dashboard (ATOP-45): başarı oranı, ortalama yanıt süresi, günlük grafik, son çalıştırmalar.

Hesaplar test_runs tablosundan yapılır: her API isteği (tek başına ya da bir koleksiyonun
adımı olarak) bir satırdır.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.collections import run_summary_fields
from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.collection import CollectionRun
from app.models.test_run import ApiTestRun
from app.schemas.collection import CollectionRunSummary
from app.schemas.reporting import ApiStat, DailyPoint, Dashboard, Totals
from app.services.test_runs import run_to_summary

router = APIRouter(
    prefix="/dashboard", tags=["Raporlama"], responses={401: {"description": "Giriş yapılmamış"}}
)


def as_utc(moment: datetime) -> datetime:
    """SQLite saat dilimini saklamaz; saat dilimi yoksa UTC kabul et."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def local_day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(settings.timezone)).astimezone(UTC)


def _api_stats(runs: list[ApiTestRun]) -> list[ApiStat]:
    groups: dict[tuple[int | None, str], list[ApiTestRun]] = defaultdict(list)
    for run in runs:
        groups[(run.api_definition_id, run.api_name)].append(run)

    stats = []
    for (api_id, name), items in groups.items():
        timed = [item.elapsed_ms for item in items if item.status_code is not None]
        latest = max(items, key=lambda item: (as_utc(item.created_at), item.id))
        stats.append(
            ApiStat(
                api_definition_id=api_id,
                api_name=name,
                runs=len(items),
                failed=sum(1 for item in items if item.status.value != "passed"),
                avg_elapsed_ms=round(sum(timed) / len(timed), 1) if timed else None,
                last_status=latest.status.value,
            )
        )
    return stats


@router.get("", response_model=Dashboard, summary="Dashboard özet bilgileri")
def dashboard(
    _: CurrentUser,
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=90, description="Son kaç gün")] = 7,
) -> Dashboard:
    zone = ZoneInfo(settings.timezone)
    today = datetime.now(zone).date()
    first_day = today - timedelta(days=days - 1)
    since = local_day_start(first_day)

    runs = list(db.scalars(select(ApiTestRun).where(ApiTestRun.created_at >= since)))

    counts = {"passed": 0, "failed": 0, "error": 0}
    daily: dict[date, dict[str, int]] = {
        first_day + timedelta(days=offset): {"passed": 0, "failed": 0, "error": 0}
        for offset in range(days)
    }
    for run in runs:
        counts[run.status.value] += 1
        day = as_utc(run.created_at).astimezone(zone).date()
        if day in daily:
            daily[day][run.status.value] += 1

    timed = [run.elapsed_ms for run in runs if run.status_code is not None]
    totals = Totals(
        runs=len(runs),
        passed=counts["passed"],
        failed=counts["failed"],
        error=counts["error"],
        success_rate=round(counts["passed"] / len(runs) * 100, 1) if runs else None,
        avg_elapsed_ms=round(sum(timed) / len(timed), 1) if timed else None,
    )

    stats = _api_stats(runs)
    failing = sorted(
        (stat for stat in stats if stat.failed), key=lambda stat: (-stat.failed, stat.api_name)
    )[:5]
    slowest = sorted(
        (stat for stat in stats if stat.avg_elapsed_ms is not None),
        key=lambda stat: -stat.avg_elapsed_ms,
    )[:5]

    recent = db.scalars(
        select(ApiTestRun).order_by(ApiTestRun.created_at.desc(), ApiTestRun.id.desc()).limit(10)
    )
    recent_collections = db.scalars(
        select(CollectionRun)
        .order_by(CollectionRun.created_at.desc(), CollectionRun.id.desc())
        .limit(5)
    )

    return Dashboard(
        days=days,
        totals=totals,
        daily=[DailyPoint(date=day, **values) for day, values in daily.items()],
        failing_apis=failing,
        slowest_apis=slowest,
        recent_runs=[run_to_summary(run) for run in recent],
        recent_collection_runs=[
            CollectionRunSummary(**run_summary_fields(run)) for run in recent_collections
        ],
    )
