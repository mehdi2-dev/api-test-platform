"""Giren adaptör: dashboard; başarı oranı, ortalama yanıt süresi, günlük grafik, son çalıştırmalar.

Hesaplar domain'de (app.domain.reporting); burada sadece HTTP şemasına çevrilir.
"""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.adapters.inbound.http.collections import run_summary_fields
from app.adapters.inbound.http.dependencies import ClockDep, CollectionRuns, CurrentUser, TestRuns
from app.application.use_cases.reporting import BuildDashboard
from app.core.config import settings
from app.schemas.collection import CollectionRunSummary
from app.schemas.reporting import ApiStat, DailyPoint, Dashboard, Totals
from app.services.test_runs import run_to_summary

router = APIRouter(
    prefix="/dashboard", tags=["Raporlama"], responses={401: {"description": "Giriş yapılmamış"}}
)


def get_dashboard(
    runs: TestRuns, collection_runs: CollectionRuns, clock: ClockDep
) -> BuildDashboard:
    return BuildDashboard(runs, collection_runs, clock, settings.timezone)


@router.get("", response_model=Dashboard, summary="Dashboard özet bilgileri")
def dashboard(
    _: CurrentUser,
    use_case: Annotated[BuildDashboard, Depends(get_dashboard)],
    days: Annotated[int, Query(ge=1, le=90, description="Son kaç gün")] = 7,
) -> Dashboard:
    data = use_case(days)
    stats = data.stats
    return Dashboard(
        days=stats.days,
        totals=Totals(**asdict(stats.totals)),
        daily=[DailyPoint(**asdict(point)) for point in stats.daily],
        failing_apis=[ApiStat(**asdict(stat)) for stat in stats.failing_apis],
        slowest_apis=[ApiStat(**asdict(stat)) for stat in stats.slowest_apis],
        recent_runs=[run_to_summary(run) for run in data.recent_runs],
        recent_collection_runs=[
            CollectionRunSummary(**run_summary_fields(run)) for run in data.recent_collection_runs
        ],
    )
