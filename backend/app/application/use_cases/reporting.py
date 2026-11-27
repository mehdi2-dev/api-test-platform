"""Use case'ler: test geçmişi ve dashboard."""

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from app.application.ports.collections import CollectionRunRepository
from app.application.ports.schedules import Clock
from app.application.ports.testing import ApiTestRunRepository
from app.domain.collections import CollectionRun
from app.domain.errors import NotFound
from app.domain.reporting import (
    DashboardStats,
    RunHistoryFilter,
    first_day,
    local_day_start,
    summarize,
)
from app.domain.testing.runs import ApiTestRun, RunStatus


class ListRecentRuns:
    def __init__(self, runs: ApiTestRunRepository) -> None:
        self._runs = runs

    def __call__(
        self, *, api_id: int | None = None, status: RunStatus | None = None, limit: int = 20
    ) -> list[ApiTestRun]:
        return self._runs.recent(api_id=api_id, status=status, limit=limit)


@dataclass
class RunPage:
    total: int
    offset: int
    limit: int
    items: list[ApiTestRun]


class SearchRunHistory:
    """Filtrelenebilir, sayfalı test geçmişi; en yeni önce."""

    def __init__(self, runs: ApiTestRunRepository) -> None:
        self._runs = runs

    def __call__(self, filters: RunHistoryFilter, offset: int, limit: int) -> RunPage:
        total, items = self._runs.search(filters, offset=offset, limit=limit)
        return RunPage(total=total, offset=offset, limit=limit, items=items)


class GetTestRun:
    def __init__(self, runs: ApiTestRunRepository) -> None:
        self._runs = runs

    def __call__(self, run_id: int) -> ApiTestRun:
        run = self._runs.get(run_id)
        if run is None:
            raise NotFound("Kayıt bulunamadı")
        return run


class GetBaseline:
    """Hata raporunda "önce nasıldı?" karşılaştırması için: aynı API'nin bu kayıttan önceki
    son BAŞARILI çalıştırması. API tanımı silinmişse veya yoksa None."""

    def __init__(self, runs: ApiTestRunRepository) -> None:
        self._runs = runs

    def __call__(self, run_id: int) -> ApiTestRun | None:
        run = GetTestRun(self._runs)(run_id)
        if run.api_definition_id is None:
            return None
        return self._runs.last_passed_before(run.api_definition_id, run.id)


@dataclass
class Dashboard:
    stats: DashboardStats
    recent_runs: list[ApiTestRun]
    recent_collection_runs: list[CollectionRun]


class BuildDashboard:
    """Başarı oranı, ortalama yanıt süresi, günlük grafik ve son çalıştırmalar."""

    def __init__(
        self,
        runs: ApiTestRunRepository,
        collection_runs: CollectionRunRepository,
        clock: Clock,
        timezone: str,
    ) -> None:
        self._runs = runs
        self._collection_runs = collection_runs
        self._clock = clock
        self._timezone = timezone

    def __call__(self, days: int) -> Dashboard:
        today: date = self._clock.now().astimezone(ZoneInfo(self._timezone)).date()
        since = local_day_start(first_day(today, days), self._timezone)
        return Dashboard(
            stats=summarize(self._runs.since(since), today, days, self._timezone),
            recent_runs=self._runs.recent(limit=10),
            recent_collection_runs=self._collection_runs.recent(limit=5),
        )
