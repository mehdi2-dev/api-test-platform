"""Dashboard ve test geçmişi şemaları (ATOP-45, ATOP-46)."""

from datetime import date

from pydantic import BaseModel, Field

from app.adapters.inbound.http.schemas.assertion import TestRunSummary
from app.adapters.inbound.http.schemas.collection import CollectionRunSummary


class Totals(BaseModel):
    runs: int
    passed: int
    failed: int
    error: int
    success_rate: float | None = Field(description="Geçen / toplam, yüzde (çalıştırma yoksa boş)")
    avg_elapsed_ms: float | None = Field(description="Cevap alınan isteklerin ortalama süresi")


class DailyPoint(BaseModel):
    date: date
    passed: int
    failed: int
    error: int


class ApiStat(BaseModel):
    api_definition_id: int | None
    api_name: str
    runs: int
    failed: int
    avg_elapsed_ms: float | None
    last_status: str | None = None


class Dashboard(BaseModel):
    days: int
    totals: Totals
    daily: list[DailyPoint]
    failing_apis: list[ApiStat] = Field(description="En çok kalan API'ler")
    slowest_apis: list[ApiStat] = Field(description="Ortalama süresi en yüksek API'ler")
    recent_runs: list[TestRunSummary]
    recent_collection_runs: list[CollectionRunSummary]


class RunPage(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[TestRunSummary]
