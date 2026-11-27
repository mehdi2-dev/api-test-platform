"""Raporlama: dashboard hesapları, test geçmişi filtresi ve önceki başarılı çalıştırma."""

from datetime import UTC, date, datetime

from app.application.use_cases.reporting import BuildDashboard, GetBaseline
from app.domain.reporting import RunHistoryFilter, summarize
from app.domain.testing.runs import ApiTestRun, RunStatus
from tests.fakes import FixedClock, InMemoryApiTestRunRepository, InMemoryCollectionRunRepository

TZ = "Europe/Istanbul"


def run(
    run_id: int,
    name: str,
    status: RunStatus,
    created: datetime,
    elapsed: float = 100.0,
    api_id: int | None = 1,
    status_code: int | None = 200,
) -> ApiTestRun:
    return ApiTestRun(
        id=run_id,
        api_definition_id=api_id,
        api_name=name,
        method="GET",
        status=status,
        status_code=status_code,
        elapsed_ms=elapsed,
        created_at=created,
    )


def test_days_are_counted_in_local_time() -> None:
    # 22:30 UTC = ertesi gün 01:30 İstanbul
    late = run(1, "A", RunStatus.PASSED, datetime(2030, 1, 6, 22, 30, tzinfo=UTC))
    stats = summarize([late], today=date(2030, 1, 7), days=2, timezone=TZ)

    assert [(p.date, p.passed) for p in stats.daily] == [
        (date(2030, 1, 6), 0),
        (date(2030, 1, 7), 1),
    ]


def test_totals_ignore_requests_without_response_in_average() -> None:
    day = datetime(2030, 1, 7, 9, 0, tzinfo=UTC)
    runs = [
        run(1, "A", RunStatus.PASSED, day, elapsed=100),
        run(2, "A", RunStatus.FAILED, day, elapsed=300),
        run(3, "B", RunStatus.ERROR, day, elapsed=0, status_code=None),
    ]

    totals = summarize(runs, date(2030, 1, 7), 1, TZ).totals

    assert (totals.runs, totals.passed, totals.failed, totals.error) == (3, 1, 1, 1)
    assert totals.success_rate == 33.3
    assert totals.avg_elapsed_ms == 200.0


def test_no_runs_means_no_rate() -> None:
    assert summarize([], date(2030, 1, 7), 7, TZ).totals.success_rate is None


def test_failing_and_slowest_apis_are_ranked() -> None:
    day = datetime(2030, 1, 7, 9, 0, tzinfo=UTC)
    runs = [
        run(1, "Yavaş", RunStatus.PASSED, day, elapsed=900, api_id=1),
        run(2, "Kırık", RunStatus.FAILED, day, elapsed=50, api_id=2),
        run(3, "Kırık", RunStatus.ERROR, day, elapsed=0, api_id=2, status_code=None),
        run(4, "Kırık", RunStatus.PASSED, day.replace(hour=10), elapsed=70, api_id=2),
    ]

    stats = summarize(runs, date(2030, 1, 7), 1, TZ)

    [failing] = stats.failing_apis
    assert (failing.api_name, failing.runs, failing.failed, failing.last_status) == (
        "Kırık",
        3,
        2,
        "passed",
    )
    assert [s.api_name for s in stats.slowest_apis] == ["Yavaş", "Kırık"]


def test_history_days_become_local_midnights() -> None:
    filters = RunHistoryFilter.for_days(
        TZ, date(2030, 1, 7), date(2030, 1, 7), name_contains="giriş"
    )

    assert filters.created_from == datetime(2030, 1, 6, 21, 0, tzinfo=UTC)
    assert filters.created_before == datetime(2030, 1, 7, 21, 0, tzinfo=UTC)
    assert filters.name_contains == "giriş"


def test_baseline_is_the_last_passed_run_before() -> None:
    runs = InMemoryApiTestRunRepository()
    day = datetime(2030, 1, 7, 9, 0, tzinfo=UTC)
    for item in [
        run(0, "A", RunStatus.PASSED, day),
        run(0, "A", RunStatus.PASSED, day),
        run(0, "A", RunStatus.FAILED, day),
        run(0, "B", RunStatus.PASSED, day, api_id=2),
        run(0, "A", RunStatus.FAILED, day),
    ]:
        item.id = None
        runs.add(item)

    assert GetBaseline(runs)(5).id == 2
    assert GetBaseline(runs)(1) is None


def test_dashboard_uses_the_clock_for_today() -> None:
    runs = InMemoryApiTestRunRepository()
    runs.add(run(0, "A", RunStatus.PASSED, datetime(2030, 1, 7, 9, 0, tzinfo=UTC)))
    runs.add(run(0, "A", RunStatus.PASSED, datetime(2029, 12, 1, 9, 0, tzinfo=UTC)))
    clock = FixedClock(datetime(2030, 1, 7, 12, 0, tzinfo=UTC))

    data = BuildDashboard(runs, InMemoryCollectionRunRepository(), clock, TZ)(7)

    assert data.stats.totals.runs == 1  # 1 Aralık 7 günlük pencerenin dışında
    assert data.stats.daily[-1].date == date(2030, 1, 7)
    assert len(data.recent_runs) == 2
