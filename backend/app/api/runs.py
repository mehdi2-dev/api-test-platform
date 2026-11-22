"""Test çalıştırma kayıtları (ATOP-35, ATOP-46, ATOP-47).

- GET /runs            son çalıştırmalar (basit liste; API sayfası kullanır)
- GET /runs/history    filtrelenebilir, sayfalı test geçmişi
- GET /runs/{id}       detay: istek, cevap, kural sonuçları
- GET /runs/{id}/baseline   aynı API'nin bundan önceki son BAŞARILI çalıştırması
                            (hata raporunda "önce nasıldı?" karşılaştırması için)
"""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.dashboard import local_day_start
from app.api.deps import CurrentUser, DbSession
from app.models.test_run import ApiTestRun, RunStatus
from app.schemas.assertion import TestRunRead, TestRunSummary
from app.schemas.reporting import RunPage
from app.services.test_runs import run_to_read, run_to_summary

router = APIRouter(
    prefix="/runs",
    tags=["Test Sonuçları"],
    responses={401: {"description": "Giriş yapılmamış"}},
)


@router.get("", response_model=list[TestRunSummary], summary="Son test çalıştırmaları")
def list_runs(
    _: CurrentUser,
    db: DbSession,
    api_id: Annotated[int | None, Query(description="Sadece bu API'nin çalıştırmaları")] = None,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[TestRunSummary]:
    query = select(ApiTestRun).order_by(ApiTestRun.created_at.desc(), ApiTestRun.id.desc())
    if api_id is not None:
        query = query.where(ApiTestRun.api_definition_id == api_id)
    if run_status is not None:
        query = query.where(ApiTestRun.status == run_status)
    return [run_to_summary(run) for run in db.scalars(query.limit(limit))]


@router.get(
    "/history",
    response_model=RunPage,
    summary="Test geçmişi (filtreli, sayfalı)",
    description="Tarihler ayarlardaki saat dilimine (Europe/Istanbul) göre gün olarak verilir.",
)
def history(
    _: CurrentUser,
    db: DbSession,
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
    filters = []
    if q:
        filters.append(ApiTestRun.api_name.ilike(f"%{q}%"))
    if api_id is not None:
        filters.append(ApiTestRun.api_definition_id == api_id)
    if run_status is not None:
        filters.append(ApiTestRun.status == run_status)
    if environment == "none":
        filters.append(ApiTestRun.environment_name.is_(None))
    elif environment:
        filters.append(ApiTestRun.environment_name == environment)
    if source == "single":
        filters.append(ApiTestRun.collection_run_id.is_(None))
    elif source == "collection":
        filters.append(ApiTestRun.collection_run_id.is_not(None))
    if date_from:
        filters.append(ApiTestRun.created_at >= local_day_start(date_from))
    if date_to:
        filters.append(ApiTestRun.created_at < local_day_start(date_to + timedelta(days=1)))

    total = db.scalar(select(func.count()).select_from(ApiTestRun).where(*filters)) or 0
    query = (
        select(ApiTestRun)
        .where(*filters)
        .order_by(ApiTestRun.created_at.desc(), ApiTestRun.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return RunPage(
        total=total,
        offset=offset,
        limit=limit,
        items=[run_to_summary(run) for run in db.scalars(query)],
    )


@router.get(
    "/{run_id}",
    response_model=TestRunRead,
    summary="Çalıştırma detayı (istek, cevap, kural sonuçları)",
    responses={404: {"description": "Kayıt bulunamadı"}},
)
def get_run(run_id: int, _: CurrentUser, db: DbSession) -> TestRunRead:
    run = db.get(ApiTestRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı")
    return run_to_read(run)


@router.get(
    "/{run_id}/baseline",
    response_model=TestRunRead | None,
    summary="Karşılaştırma için önceki başarılı çalıştırma",
    description=(
        "Aynı API'nin bu kayıttan önceki son başarılı (passed) çalıştırması. Yoksa null döner."
    ),
    responses={404: {"description": "Kayıt bulunamadı"}},
)
def baseline(run_id: int, _: CurrentUser, db: DbSession) -> TestRunRead | None:
    run = db.get(ApiTestRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı")
    if run.api_definition_id is None:
        return None
    previous = db.scalar(
        select(ApiTestRun)
        .where(
            ApiTestRun.api_definition_id == run.api_definition_id,
            ApiTestRun.status == RunStatus.PASSED,
            ApiTestRun.id < run.id,
        )
        .order_by(ApiTestRun.id.desc())
        .limit(1)
    )
    return run_to_read(previous) if previous else None
