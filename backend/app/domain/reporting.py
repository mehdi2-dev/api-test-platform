"""Raporlama: dashboard istatistikleri ve test geçmişi filtresi.

Hesaplar test çalıştırma kayıtlarından yapılır: her API isteği (tek başına ya da bir
koleksiyonun adımı olarak) bir kayıttır. Günler ayarlardaki saat dilimine göre sayılır.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.domain.testing.runs import ApiTestRun, RunStatus

STATUSES = ("passed", "failed", "error")


def as_utc(moment: datetime) -> datetime:
    """Bazı veritabanları (SQLite) saat dilimini saklamaz; saat dilimi yoksa UTC kabul et."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def local_day_start(day: date, timezone: str) -> datetime:
    """Yerel saatle günün başlangıcı, UTC olarak."""
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(timezone)).astimezone(UTC)


# --- Test geçmişi ---

Source = Literal["all", "single", "collection"]


@dataclass(frozen=True)
class RunHistoryFilter:
    """Test geçmişinde arama. environment="none" ortamsız çalıştırmaları seçer."""

    name_contains: str | None = None
    api_id: int | None = None
    status: RunStatus | None = None
    environment: str | None = None
    source: Source = "all"
    """single: tek API, collection: koleksiyon adımı"""
    created_from: datetime | None = None
    created_before: datetime | None = None

    @classmethod
    def for_days(
        cls,
        timezone: str,
        date_from: date | None = None,
        date_to: date | None = None,
        **filters,
    ) -> "RunHistoryFilter":
        """Gün aralığını (iki gün de dahil) yerel saate göre UTC anlara çevirir."""
        return cls(
            created_from=local_day_start(date_from, timezone) if date_from else None,
            created_before=(
                local_day_start(date_to + timedelta(days=1), timezone) if date_to else None
            ),
            **filters,
        )


# --- Dashboard ---


@dataclass
class Totals:
    runs: int
    passed: int
    failed: int
    error: int
    success_rate: float | None
    """Geçen / toplam, yüzde (çalıştırma yoksa boş)"""
    avg_elapsed_ms: float | None
    """Cevap alınan isteklerin ortalama süresi"""


@dataclass
class DailyPoint:
    date: date
    passed: int = 0
    failed: int = 0
    error: int = 0


@dataclass
class ApiStat:
    api_definition_id: int | None
    api_name: str
    runs: int
    failed: int
    avg_elapsed_ms: float | None
    last_status: str | None = None


@dataclass
class DashboardStats:
    days: int
    totals: Totals
    daily: list[DailyPoint]
    failing_apis: list[ApiStat] = field(default_factory=list)
    """En çok kalan API'ler"""
    slowest_apis: list[ApiStat] = field(default_factory=list)
    """Ortalama süresi en yüksek API'ler"""


def first_day(today: date, days: int) -> date:
    return today - timedelta(days=days - 1)


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _api_stats(runs: list[ApiTestRun]) -> list[ApiStat]:
    groups: dict[tuple[int | None, str], list[ApiTestRun]] = defaultdict(list)
    for run in runs:
        groups[(run.api_definition_id, run.api_name)].append(run)

    stats = []
    for (api_id, name), items in groups.items():
        latest = max(items, key=lambda item: (as_utc(item.created_at), item.id))
        stats.append(
            ApiStat(
                api_definition_id=api_id,
                api_name=name,
                runs=len(items),
                failed=sum(1 for item in items if item.status != RunStatus.PASSED),
                avg_elapsed_ms=_average(
                    [item.elapsed_ms for item in items if item.status_code is not None]
                ),
                last_status=latest.status.value,
            )
        )
    return stats


def summarize(runs: list[ApiTestRun], today: date, days: int, timezone: str) -> DashboardStats:
    """Son `days` günün çalıştırmalarından özet, günlük dağılım ve API sıralamaları."""
    zone = ZoneInfo(timezone)
    start = first_day(today, days)
    daily = {
        start + timedelta(days=offset): DailyPoint(start + timedelta(days=offset))
        for offset in range(days)
    }
    counts = dict.fromkeys(STATUSES, 0)

    for run in runs:
        status = run.status.value
        counts[status] += 1
        point = daily.get(as_utc(run.created_at).astimezone(zone).date())
        if point is not None:
            setattr(point, status, getattr(point, status) + 1)

    totals = Totals(
        runs=len(runs),
        passed=counts["passed"],
        failed=counts["failed"],
        error=counts["error"],
        success_rate=round(counts["passed"] / len(runs) * 100, 1) if runs else None,
        avg_elapsed_ms=_average([run.elapsed_ms for run in runs if run.status_code is not None]),
    )

    stats = _api_stats(runs)
    failing = sorted(
        (stat for stat in stats if stat.failed), key=lambda stat: (-stat.failed, stat.api_name)
    )[:5]
    slowest = sorted(
        (stat for stat in stats if stat.avg_elapsed_ms is not None),
        key=lambda stat: -stat.avg_elapsed_ms,
    )[:5]

    return DashboardStats(
        days=days,
        totals=totals,
        daily=list(daily.values()),
        failing_apis=failing,
        slowest_apis=slowest,
    )
