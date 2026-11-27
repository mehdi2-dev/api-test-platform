"""Dashboard, test geçmişi, hata raporu karşılaştırması ve bildirimler (ATOP-45..48)."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.inbound.http.apis import get_http_transport
from app.adapters.outbound.notifications import senders as notifications
from app.adapters.outbound.security.crypto import decrypt_text
from app.domain.notifications import NotificationChannel
from app.domain.testing.runs import ApiTestRun
from app.domain.users import Role
from app.main import app

SLACK = "https://hooks.slack.test/services/T000/B000/gizli-anahtar"


class FakeServer:
    """srv.test: API'ler; hooks.*: bildirim adresleri. Gelen istekleri saklar."""

    def __init__(self) -> None:
        self.status = 200
        self.hook_status = 200
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host.startswith("hooks."):
            return httpx.Response(self.hook_status, text="ok")
        return httpx.Response(self.status, json={"durum": "ok"})

    def hooks(self) -> list[httpx.Request]:
        return [item for item in self.requests if item.url.host.startswith("hooks.")]


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(fake)
    yield fake
    app.dependency_overrides.pop(get_http_transport, None)


@pytest.fixture
def admin(make_user, login) -> dict[str, str]:
    make_user("admin@apitest.com", Role.ADMIN)
    return login("admin@apitest.com")


@pytest.fixture
def tester(make_user, login) -> dict[str, str]:
    make_user("tester@apitest.com", Role.TESTER)
    return login("tester@apitest.com")


@pytest.fixture
def viewer(make_user, login) -> dict[str, str]:
    make_user("viewer@apitest.com", Role.VIEWER)
    return login("viewer@apitest.com")


def make_api(api: TestClient, headers, name: str = "Ürünler", path: str = "/products") -> int:
    response = api.post(
        "/api/apis",
        json={
            "name": name,
            "url": f"https://srv.test{path}",
            "assertions": [{"type": "status_code", "operator": "equals", "expected": "200"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def run_api(api: TestClient, headers, api_id: int) -> dict:
    response = api.post(f"/api/apis/{api_id}/run", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def make_collection(api: TestClient, headers, api_id: int) -> int:
    response = api.post(
        "/api/collections",
        json={"name": "Gece testi", "items": [{"api_definition_id": api_id}]},
        headers=headers,
    )
    return response.json()["id"]


def run_collection(api: TestClient, headers, collection_id: int) -> dict:
    response = api.post(f"/api/collections/{collection_id}/run", json={}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- Dashboard (ATOP-45) ---


def test_empty_dashboard(api: TestClient, viewer) -> None:
    data = api.get("/api/dashboard", headers=viewer).json()
    assert data["totals"]["runs"] == 0
    assert data["totals"]["success_rate"] is None
    assert len(data["daily"]) == 7
    assert data["recent_runs"] == []


def test_dashboard_counts_and_rates(api: TestClient, tester, server) -> None:
    good = make_api(api, tester, "İyi", "/good")
    bad = make_api(api, tester, "Kötü", "/bad")

    run_api(api, tester, good)
    run_api(api, tester, good)
    run_api(api, tester, good)
    server.status = 500
    run_api(api, tester, bad)

    data = api.get("/api/dashboard?days=30", headers=tester).json()
    totals = data["totals"]
    assert (totals["runs"], totals["passed"], totals["failed"]) == (4, 3, 1)
    assert totals["success_rate"] == 75.0
    assert totals["avg_elapsed_ms"] is not None
    assert len(data["daily"]) == 30
    assert sum(day["passed"] for day in data["daily"]) == 3
    assert [item["api_name"] for item in data["failing_apis"]] == ["Kötü"]
    assert data["failing_apis"][0]["last_status"] == "failed"
    assert len(data["recent_runs"]) == 4


def test_dashboard_requires_login(api: TestClient) -> None:
    assert api.get("/api/dashboard").status_code == 401


# --- Test geçmişi (ATOP-46) ---


def test_history_filters_and_pagination(api: TestClient, tester, server) -> None:
    products = make_api(api, tester, "Ürünler", "/products")
    orders = make_api(api, tester, "Siparişler", "/orders")
    for _ in range(3):
        run_api(api, tester, products)
    server.status = 404
    run_api(api, tester, orders)
    collection_id = make_collection(api, tester, orders)
    run_collection(api, tester, collection_id)

    def history(**params) -> dict:
        response = api.get("/api/runs/history", params=params, headers=tester)
        assert response.status_code == 200, response.text
        return response.json()

    everything = history()
    assert everything["total"] == 5

    page = history(limit=2, offset=2)
    assert (page["total"], len(page["items"])) == (5, 2)

    assert history(status="failed")["total"] == 2
    assert history(q="sipariş")["total"] == 2
    assert history(api_id=products)["total"] == 3
    assert history(source="collection")["total"] == 1
    assert history(source="single")["total"] == 4
    assert history(environment="none")["total"] == 5
    assert history(environment="Prod")["total"] == 0

    today = datetime.now(UTC).date()
    assert history(date_from=str(today - timedelta(days=1)))["total"] == 5
    assert history(date_to=str(today - timedelta(days=2)))["total"] == 0


# --- Hata raporu: karşılaştırma (ATOP-47) ---


def test_baseline_is_last_passing_run(api: TestClient, tester, server) -> None:
    api_id = make_api(api, tester)
    first = run_api(api, tester, api_id)
    passing = run_api(api, tester, api_id)
    server.status = 500
    failing = run_api(api, tester, api_id)

    baseline = api.get(f"/api/runs/{failing['id']}/baseline", headers=tester)
    assert baseline.status_code == 200
    assert baseline.json()["id"] == passing["id"]
    assert baseline.json()["response"]["status_code"] == 200

    # İlk çalıştırmanın öncesinde başarılı kayıt yok
    assert api.get(f"/api/runs/{first['id']}/baseline", headers=tester).json() is None
    assert api.get("/api/runs/999/baseline", headers=tester).status_code == 404


# --- Bildirimler (ATOP-48) ---


def make_channel(api: TestClient, headers, **extra) -> dict:
    data = {"name": "QA kanalı", "type": "slack", "target": SLACK} | extra
    response = api.post("/api/notifications", json=data, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_channel_target_is_encrypted_and_hidden(
    api: TestClient, admin, db_session: Session
) -> None:
    channel = make_channel(api, admin)
    assert channel["target_preview"] == "https://hooks.slack.test/****"
    assert "gizli-anahtar" not in json.dumps(channel)

    row = db_session.get(NotificationChannel, channel["id"])
    assert "gizli-anahtar" not in row.target_encrypted
    assert decrypt_text(row.target_encrypted) == SLACK


@pytest.mark.parametrize(
    ("channel_type", "target"),
    [("slack", "hooks.slack.test/x"), ("email", "gecersiz"), ("email", "a@b.com, yanlis")],
)
def test_invalid_targets(api: TestClient, admin, channel_type, target) -> None:
    response = api.post(
        "/api/notifications",
        json={"name": "X", "type": channel_type, "target": target},
        headers=admin,
    )
    assert response.status_code == 422


def test_only_admin_manages_channels(api: TestClient, admin, tester, viewer) -> None:
    channel = make_channel(api, admin)
    url = f"/api/notifications/{channel['id']}"

    assert api.get("/api/notifications", headers=tester).status_code == 200
    assert api.get("/api/notifications", headers=viewer).status_code == 403
    body = {"name": "Y", "type": "slack", "target": SLACK}
    assert api.post("/api/notifications", json=body, headers=tester).status_code == 403
    assert api.patch(url, json={"enabled": False}, headers=tester).status_code == 403
    assert api.delete(url, headers=tester).status_code == 403
    assert api.delete(url, headers=admin).status_code == 204


def test_send_test_message(api: TestClient, admin, server) -> None:
    channel = make_channel(api, admin)
    result = api.post(f"/api/notifications/{channel['id']}/test", headers=admin).json()

    assert result == {"ok": True, "error": None}
    [hook] = server.hooks()
    assert "deneme" in json.loads(hook.content)["text"]
    listed = api.get("/api/notifications", headers=admin).json()[0]
    assert listed["last_status"] == "ok"


def test_failed_collection_sends_slack_message(api: TestClient, admin, server) -> None:
    make_channel(api, admin)
    api_id = make_api(api, admin, "Ödeme", "/pay")
    collection_id = make_collection(api, admin, api_id)

    server.status = 503
    result = run_collection(api, admin, collection_id)
    assert result["status"] == "failed"

    [hook] = server.hooks()
    text = json.loads(hook.content)["text"]
    assert "Gece testi" in text and "KALDI" in text
    assert "Ödeme" in text and "503" in text
    assert "/collections/" in text


def test_passed_collection_notifies_only_always_channels(api: TestClient, admin, server) -> None:
    make_channel(api, admin, name="Sadece hata")
    make_channel(
        api,
        admin,
        name="Hepsi",
        type="webhook",
        target="https://hooks.ci.test/x",
        notify_on="always",
    )
    api_id = make_api(api, admin)
    run_collection(api, admin, make_collection(api, admin, api_id))

    [hook] = server.hooks()
    assert hook.url.host == "hooks.ci.test"
    payload = json.loads(hook.content)
    assert payload["status"] == "passed"
    assert payload["collection"]["name"] == "Gece testi"
    assert payload["failed_steps"] == []


def test_disabled_channel_is_skipped(api: TestClient, admin, server) -> None:
    make_channel(api, admin, enabled=False)
    server.status = 500
    run_collection(api, admin, make_collection(api, admin, make_api(api, admin)))
    assert server.hooks() == []


def test_broken_channel_does_not_break_run(api: TestClient, admin, server) -> None:
    channel = make_channel(api, admin)
    server.status = 500
    server.hook_status = 404

    result = run_collection(api, admin, make_collection(api, admin, make_api(api, admin)))
    assert result["status"] == "failed"  # test sonucu etkilenmedi

    listed = api.get("/api/notifications", headers=admin).json()
    saved = next(item for item in listed if item["id"] == channel["id"])
    assert saved["last_status"] == "error"
    assert "404" in saved["last_error"]


def test_email_channel(api: TestClient, admin, server, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            sent.append(("tls",))

        def login(self, user, password):
            sent.append(("login", user))

        def send_message(self, message):
            sent.append(("send", message["To"], message["Subject"], message.get_content()))

    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notifications.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(notifications.settings, "smtp_user", "")

    make_channel(api, admin, name="Mail", type="email", target="qa@firma.com, lead@firma.com")
    server.status = 500
    run_collection(api, admin, make_collection(api, admin, make_api(api, admin)))

    assert sent[0] == ("connect", "smtp.test", 587)
    assert ("tls",) in sent
    _, to, subject, body = sent[-1]
    assert to == "qa@firma.com, lead@firma.com"
    assert "KALDI" in subject
    assert "Gece testi" in body


def test_email_without_smtp_is_recorded_as_error(api: TestClient, admin, server) -> None:
    channel = make_channel(api, admin, name="Mail", type="email", target="qa@firma.com")
    result = api.post(f"/api/notifications/{channel['id']}/test", headers=admin).json()
    assert result["ok"] is False
    assert "SMTP" in result["error"]


def test_failure_reason_uses_first_failed_rule(
    api: TestClient, admin, server, db_session: Session
) -> None:
    make_channel(api, admin)
    server.status = 401
    run_collection(api, admin, make_collection(api, admin, make_api(api, admin)))

    text = json.loads(server.hooks()[0].content)["text"]
    assert "Beklenen 200, gelen 401" in text
    assert db_session.query(ApiTestRun).count() == 1
