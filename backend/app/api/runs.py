"""Test çalıştırma kayıtları (ATOP-35).

Şimdilik son çalıştırmaları listelemek ve birinin detayını görmek için. Test geçmişi
ekranı ve dashboard (Epic 7) bu endpoint'leri genişletecek.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.test_run import ApiTestRun, RunStatus
from app.schemas.assertion import TestRunRead, TestRunSummary
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
