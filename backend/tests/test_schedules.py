"""Asenkron çalıştırma, zamanlamalar ve canlı durum (ATOP-41..44) testleri.

Celery/Redis kullanılmaz: kuyruğa atma işi bir listeye yazılır, worker'ın yaptığı iş
(execute_collection_run) testte elle çağrılır.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.inbound.http.collections import get_enqueuer
from app.composition import dispatch_due, execute_collection_run
from app.domain import cron
from app.domain.collections import CollectionRun
from app.domain.schedules import Schedule
from app.domain.users import Role
from app.main import app

IST = ZoneInfo("Europe/Istanbul")


def ok_server(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


TRANSPORT = httpx.MockTransport(ok_server)


@pytest.fixture
def tester(make_user, login) -> dict[str, str]:
    make_user("tester@apitest.com", Role.TESTER)
    return login("tester@apitest.com")


@pytest.fixture
def viewer(make_user, login) -> dict[str, str]:
    make_user("viewer@apitest.com", Role.VIEWER)
    return login("viewer@apitest.com")


@pytest.fixture
def queue() -> Iterator[list[tuple[int, int | None, bool]]]:
    """Kuyruğa atılan işleri biriktirir."""
    calls: list[tuple[int, int | None, bool]] = []
    app.dependency_overrides[get_enqueuer] = lambda: lambda *args: calls.append(args)
    yield calls
    app.dependency_overrides.pop(get_enqueuer, None)


def make_collection(api: TestClient, headers, method: str = "GET", name: str = "Akış") -> int:
    api_response = api.post(
        "/api/apis",
        json={
            "name": f"{method} kontrol",
            "method": method,
            "url": "https://srv.test/ok",
            "assertions": [{"type": "status_code", "operator": "equals", "expected": "200"}],
        },
        headers=headers,
    )
    assert api_response.status_code == 201, api_response.text
    response = api.post(
        "/api/collections",
        json={"name": name, "items": [{"api_definition_id": api_response.json()["id"]}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def local(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=IST)


# --- Cron (ATOP-42) ---


@pytest.mark.parametrize(
    ("expression", "after", "expected"),
    [
        ("*/5 * * * *", "2026-11-22 19:03", "2026-11-22 19:05"),
        ("*/5 * * * *", "2026-11-22 19:05", "2026-11-22 19:10"),
        ("0 9 * * 1-5", "2026-11-22 19:00", "2026-11-23 09:00"),  # pazar -> pazartesi
        ("0 9 * * 1-5", "2026-11-27 10:00", "2026-11-30 09:00"),  # cuma -> pazartesi
        ("0 0 1 * *", "2026-11-22 19:00", "2026-12-01 00:00"),
        ("@daily", "2026-12-31 23:59", "2027-01-01 00:00"),
        ("0 0 13 * 5", "2026-11-22 00:00", "2026-11-27 00:00"),  # 13'ü VEYA cuma
        ("30 8-18/2 * * *", "2026-11-22 19:00", "2026-11-23 08:30"),
        ("0 0 29 2 *", "2026-11-22 00:00", "2028-02-29 00:00"),
        ("0 0 * * 7", "2026-11-22 00:00", "2026-11-29 00:00"),  # 7 = pazar
    ],
)
def test_cron_next_run(expression, after, expected) -> None:
    result = cron.next_after(cron.parse(expression), local(after), "Europe/Istanbul")
    assert result.tzinfo is not None
    assert result.astimezone(IST) == local(expected)


@pytest.mark.parametrize(
    "expression",
    ["* * * *", "60 * * * *", "*/0 * * * *", "a b c d e", "5-1 * * * *", "0 0 30 2 *", ""],
)
def test_cron_invalid(expression) -> None:
    with pytest.raises(ValueError):
        cron.validate(expression)


# --- Zamanlama CRUD (ATOP-43) ---


def test_create_schedule_sets_next_run(api: TestClient, tester) -> None:
    collection_id = make_collection(api, tester)
    response = api.post(
        "/api/schedules",
        json={"collection_id": collection_id, "cron": "  */5   * * * * "},
        headers=tester,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["cron"] == "*/5 * * * *"
    assert data["collection_name"] == "Akış"
    assert data["next_run_at"] is not None
    assert data["enabled"] is True


def test_disable_clears_next_run_and_enable_restores(api: TestClient, tester) -> None:
    collection_id = make_collection(api, tester)
    schedule = api.post(
        "/api/schedules", json={"collection_id": collection_id, "cron": "@hourly"}, headers=tester
    ).json()
    url = f"/api/schedules/{schedule['id']}"

    assert api.patch(url, json={"enabled": False}, headers=tester).json()["next_run_at"] is None
    assert api.patch(url, json={"enabled": True}, headers=tester).json()["next_run_at"]


@pytest.mark.parametrize("expression", ["* * *", "99 * * * *", "0 0 31 2 *"])
def test_invalid_cron_is_422(api: TestClient, tester, expression) -> None:
    collection_id = make_collection(api, tester)
    response = api.post(
        "/api/schedules", json={"collection_id": collection_id, "cron": expression}, headers=tester
    )
    assert response.status_code == 422


def test_preview_returns_next_runs(api: TestClient, viewer) -> None:
    response = api.get("/api/schedules/preview", params={"cron": "0 9 * * 1-5"}, headers=viewer)
    assert response.status_code == 200
    data = response.json()
    assert len(data["next_runs"]) == 5
    assert data["timezone"] == "Europe/Istanbul"
    assert api.get("/api/schedules/preview?cron=x", headers=viewer).status_code == 422


def test_viewer_can_list_but_not_manage(api: TestClient, tester, viewer) -> None:
    collection_id = make_collection(api, tester)
    schedule = api.post(
        "/api/schedules", json={"collection_id": collection_id, "cron": "@daily"}, headers=tester
    ).json()

    assert len(api.get("/api/schedules", headers=viewer).json()) == 1
    body = {"collection_id": collection_id, "cron": "@daily"}
    assert api.post("/api/schedules", json=body, headers=viewer).status_code == 403
    url = f"/api/schedules/{schedule['id']}"
    assert api.patch(url, json={"enabled": False}, headers=viewer).status_code == 403
    assert api.delete(url, headers=viewer).status_code == 403
    assert api.delete(url, headers=tester).status_code == 204


def test_production_schedule_needs_confirmation(api: TestClient, tester) -> None:
    collection_id = make_collection(api, tester, method="DELETE")
    prod = api.post(
        "/api/environments", json={"name": "Prod", "is_production": True}, headers=tester
    ).json()
    body = {"collection_id": collection_id, "cron": "@daily", "environment_id": prod["id"]}

    response = api.post("/api/schedules", json=body, headers=tester)
    assert response.status_code == 422
    assert "DELETE" in response.json()["detail"]

    confirmed = api.post("/api/schedules", json=body | {"confirm_production": True}, headers=tester)
    assert confirmed.status_code == 201
    assert confirmed.json()["is_production"] is True


# --- Asenkron çalıştırma ve canlı durum (ATOP-41, ATOP-44) ---


def test_async_run_goes_queued_then_completed(
    api: TestClient, tester, queue, db_session: Session
) -> None:
    collection_id = make_collection(api, tester)

    response = api.post(f"/api/collections/{collection_id}/run-async", json={}, headers=tester)
    assert response.status_code == 202, response.text
    queued = response.json()
    assert queued["state"] == "queued"
    assert queued["status"] is None
    assert queued["total_steps"] == 1
    assert queue == [(queued["id"], None, False)]

    detail_url = f"/api/collections/{collection_id}/runs/{queued['id']}"
    assert api.get(detail_url, headers=tester).json()["state"] == "queued"

    # Worker'ın yaptığı iş
    execute_collection_run(db_session, queued["id"], None, False, transport=TRANSPORT)

    done = api.get(detail_url, headers=tester).json()
    assert done["state"] == "completed"
    assert done["status"] == "passed"
    assert done["passed_steps"] == 1
    assert len(done["step_runs"]) == 1

    # Aynı iş ikinci kez gelirse tekrar çalışmaz
    execute_collection_run(db_session, queued["id"], None, False, transport=TRANSPORT)
    assert len(api.get(detail_url, headers=tester).json()["step_runs"]) == 1


def test_async_run_checks_production_before_queueing(api: TestClient, tester, queue) -> None:
    collection_id = make_collection(api, tester, method="POST")
    prod = api.post(
        "/api/environments", json={"name": "Prod", "is_production": True}, headers=tester
    ).json()

    url = f"/api/collections/{collection_id}/run-async"
    response = api.post(url, json={"environment_id": prod["id"]}, headers=tester)
    assert response.status_code == 409
    assert queue == []

    response = api.post(
        url, json={"environment_id": prod["id"], "confirm_production": True}, headers=tester
    )
    assert response.status_code == 202
    assert response.json()["environment_name"] == "Prod"
    assert queue[0][1:] == (prod["id"], True)


def test_queue_failure_marks_run_as_error(api: TestClient, tester) -> None:
    def broken(*_: object) -> None:
        raise ConnectionError("redis kapalı")

    app.dependency_overrides[get_enqueuer] = lambda: broken
    try:
        collection_id = make_collection(api, tester)
        response = api.post(f"/api/collections/{collection_id}/run-async", json={}, headers=tester)
    finally:
        app.dependency_overrides.pop(get_enqueuer, None)

    assert response.status_code == 503
    runs = api.get(f"/api/collections/{collection_id}/runs", headers=tester).json()
    assert runs[0]["state"] == "completed"
    assert runs[0]["status"] == "error"
    assert "Kuyruğa eklenemedi" in runs[0]["error"]


def test_worker_marks_error_when_production_not_confirmed(
    api: TestClient, tester, queue, db_session: Session
) -> None:
    collection_id = make_collection(api, tester, method="POST")
    run_id = api.post(
        f"/api/collections/{collection_id}/run-async", json={}, headers=tester
    ).json()["id"]
    prod = api.post(
        "/api/environments", json={"name": "Prod", "is_production": True}, headers=tester
    ).json()

    # Kuyruktayken ortam Production'a çevrilmiş gibi: worker yine de çalıştırmamalı
    result = execute_collection_run(db_session, run_id, prod["id"], False, transport=TRANSPORT)
    assert result.status.value == "error"
    assert "Production" in result.error


# --- Zamanlanmış çalıştırma (ATOP-42) ---


def test_dispatch_due_runs_schedule_and_advances(
    api: TestClient, tester, db_session: Session
) -> None:
    collection_id = make_collection(api, tester)
    schedule_id = api.post(
        "/api/schedules",
        json={"collection_id": collection_id, "cron": "*/5 * * * *"},
        headers=tester,
    ).json()["id"]

    now = datetime.now(UTC)
    schedule = db_session.get(Schedule, schedule_id)
    schedule.next_run_at = now - timedelta(minutes=1)  # zamanı geçmiş
    db_session.commit()

    queued: list[tuple] = []
    created = dispatch_due(db_session, now, lambda *args: queued.append(args))
    assert len(created) == 1
    assert queued == [(created[0], None, False)]

    db_session.expire_all()
    schedule = db_session.get(Schedule, schedule_id)
    assert schedule.last_run_id == created[0]
    assert schedule.next_run_at.replace(tzinfo=UTC) > now

    run = db_session.get(CollectionRun, created[0])
    assert (run.state, run.trigger, run.schedule_id) == ("queued", "schedule", schedule_id)

    execute_collection_run(db_session, created[0], None, False, transport=TRANSPORT)
    listed = api.get("/api/schedules", headers=tester).json()[0]
    assert listed["last_run_status"] == "passed"
    assert listed["last_run_state"] == "completed"

    # Zamanı gelmemiş plan tekrar çalışmaz
    assert dispatch_due(db_session, now, lambda *args: queued.append(args)) == []


def test_dispatch_skips_disabled(api: TestClient, tester, db_session: Session) -> None:
    collection_id = make_collection(api, tester)
    schedule_id = api.post(
        "/api/schedules",
        json={"collection_id": collection_id, "cron": "@hourly", "enabled": False},
        headers=tester,
    ).json()["id"]
    schedule = db_session.get(Schedule, schedule_id)
    schedule.next_run_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    assert dispatch_due(db_session, datetime.now(UTC), lambda *args: None) == []


def test_run_now(api: TestClient, tester, queue) -> None:
    collection_id = make_collection(api, tester)
    schedule_id = api.post(
        "/api/schedules", json={"collection_id": collection_id, "cron": "@daily"}, headers=tester
    ).json()["id"]

    response = api.post(f"/api/schedules/{schedule_id}/run-now", headers=tester)
    assert response.status_code == 202
    data = response.json()
    assert (data["state"], data["trigger"], data["schedule_id"]) == (
        "queued",
        "schedule",
        schedule_id,
    )
    assert len(queue) == 1
