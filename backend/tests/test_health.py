"""Health endpoint testleri. Gerçek DB/Redis gerektirmez; kontroller taklit edilir."""

import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_ping(client: TestClient) -> None:
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"ping": "pong"}


def test_health_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "check_database", lambda: "ok")
    monkeypatch.setattr(health, "check_redis", lambda: "ok")

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "ok", "redis": "ok"}


def test_health_returns_503_when_dependency_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "check_database", lambda: "error")
    monkeypatch.setattr(health, "check_redis", lambda: "ok")

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_celery_add_task_runs_eagerly() -> None:
    from app.worker.celery_app import celery_app
    from app.worker.tasks import add

    celery_app.conf.task_always_eager = True
    try:
        assert add.delay(2, 3).get() == 5
    finally:
        celery_app.conf.task_always_eager = False


def test_health_documents_503_in_openapi(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/api/health"]["get"]["responses"]
    assert "503" in responses
