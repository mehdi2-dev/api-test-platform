"""Giren adaptör: test çalıştırma kayıtları.

- GET /runs            son çalıştırmalar (basit liste; API sayfası kullanır)
- GET /runs/history    filtrelenebilir, sayfalı test geçmişi
- GET /runs/{id}       detay: istek, cevap, kural sonuçları
- GET /runs/{id}/baseline   aynı API'nin bundan önceki son BAŞARILI çalıştırması
                            (hata raporunda "önce nasıldı?" karşılaştırması için)
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.adapters.inbound.http.dependencies import CurrentUser, TestRuns
from app.application.use_cases.reporting import (
    GetBaseline,
    GetTestRun,
    ListRecentRuns,
    SearchRunHistory,
)
from app.core.config import settings
from app.domain.reporting import RunHistoryFilter
from app.domain.testing.runs import RunStatus
from app.schemas.assertion import TestRunRead, TestRunSummary
from app.schemas.reporting import RunPage
from app.services.test_runs import run_to_read, run_to_summary

router = APIRouter(
    prefix="/runs",
    tags=["Test Sonuçları"],
    responses={401: {"description": "Giriş yapılmamış"}},
)
NOT_FOUND = {404: {"description": "Kayıt bulunamadı"}}


def get_recent(runs: TestRuns) -> ListRecentRuns:
    return ListRecentRuns(runs)


def get_history(runs: TestRuns) -> SearchRunHistory:
    return SearchRunHistory(runs)


def get_run_use_case(runs: TestRuns) -> GetTestRun:
    return GetTestRun(runs)


def get_baseline(runs: TestRuns) -> GetBaseline:
    return GetBaseline(runs)


@router.get("", response_model=list[TestRunSummary], summary="Son test çalıştırmaları")
def list_runs(
    _: CurrentUser,
    use_case: Annotated[ListRecentRuns, Depends(get_recent)],
    api_id: Annotated[int | None, Query(description="Sadece bu API'nin çalıştırmaları")] = None,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[TestRunSummary]:
    return [run_to_summary(run) for run in use_case(api_id=api_id, status=run_status, limit=limit)]


@router.get(
    "/history",
    response_model=RunPage,
    summary="Test geçmişi (filtreli, sayfalı)",
    description="Tarihler ayarlardaki saat dilimine (Europe/Istanbul) göre gün olarak verilir.",
)
def history(
    _: CurrentUser,
    use_case: Annotated[SearchRunHistory, Depends(get_history)],
    q: Annotated[str | None, Query(description="API adında ara")] = None,
    api_id: int | None = None,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    environment: Annotated[str | None, Query(description="Ortam adı; 'none' = ortamsız")] = None,
    source: Annotated[
        Literal["all", "single", "collection"],
        Query(description="single: tek API, collection: koleksiyon adımı"),
    ] = "all",
    date_from: date | None = None,
    date_to: date | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> RunPage:
    filters = RunHistoryFilter.for_days(
        settings.timezone,
        date_from,
        date_to,
        name_contains=q,
        api_id=api_id,
        status=run_status,
        environment=environment,
        source=source,
    )
    page = use_case(filters, offset, limit)
    return RunPage(
        total=page.total,
        offset=page.offset,
        limit=page.limit,
        items=[run_to_summary(run) for run in page.items],
    )


@router.get(
    "/{run_id}",
    response_model=TestRunRead,
    summary="Çalıştırma detayı (istek, cevap, kural sonuçları)",
    responses=NOT_FOUND,
)
def get_run(
    run_id: int,
    _: CurrentUser,
    use_case: Annotated[GetTestRun, Depends(get_run_use_case)],
) -> TestRunRead:
    return run_to_read(use_case(run_id))


@router.get(
    "/{run_id}/baseline",
    response_model=TestRunRead | None,
    summary="Karşılaştırma için önceki başarılı çalıştırma",
    description=(
        "Aynı API'nin bu kayıttan önceki son başarılı (passed) çalıştırması. Yoksa null döner."
    ),
    responses=NOT_FOUND,
)
def baseline(
    run_id: int,
    _: CurrentUser,
    use_case: Annotated[GetBaseline, Depends(get_baseline)],
) -> TestRunRead | None:
    previous = use_case(run_id)
    return run_to_read(previous) if previous else None
