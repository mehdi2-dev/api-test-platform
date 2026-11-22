"""Uçtan uca kabul testi (ATOP-58).

Proje tanımındaki teslim kriterlerini gerçek akışla doğrular: demo verileri yüklenir,
üç örnek koleksiyon "Demo" ortamında çalıştırılır ve hepsinin geçmesi beklenir.

Platform istekleri demo servisine gerçekten gönderir; ağ yerine istekler doğrudan demo
uygulamasına yönlendirilir (Docker gerekmez).
"""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.apis import get_http_transport
from app.demo.main import app as demo_app
from app.demo.main import store
from app.main import app
from app.models.user import Role
from app.schemas.api_definition import MASK
from app.services.demo_seed import example_files


@pytest.fixture
def demo_network() -> Iterator[list[httpx.Request]]:
    """http://demo:8001'e giden istekleri demo uygulamasına iletir."""
    store.reset()
    demo = TestClient(demo_app)
    sent: list[httpx.Request] = []

    def forward(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        response = demo.request(
            request.method,
            request.url.raw_path.decode(),
            headers={
                k: v for k, v in request.headers.items() if k not in ("host", "content-length")
            },
            content=request.content,
        )
        return httpx.Response(
            response.status_code, headers=response.headers, content=response.content
        )

    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(forward)
    yield sent
    app.dependency_overrides.pop(get_http_transport, None)
    store.reset()


@pytest.fixture
def admin(make_user, login) -> dict[str, str]:
    make_user("admin@apitest.com", Role.ADMIN)
    return login("admin@apitest.com")


@pytest.fixture
def seeded(api: TestClient, admin) -> dict:
    response = api.post("/api/collections/seed-demo", headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def run(api: TestClient, headers, collection_id: int, environment_id: int) -> dict:
    response = api.post(
        f"/api/collections/{collection_id}/run",
        json={"environment_id": environment_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def explain(result: dict) -> str:
    """Kalan adımları okunur hale getirir (test kırmızı olursa ne olduğu görünsün)."""
    lines = []
    for step in result["steps"]:
        if step["status"] == "passed":
            continue
        detail = result["step_runs"].get(str(step["test_run_id"]), {})
        failed = [r["message"] for r in detail.get("assertion_results", []) if not r["passed"]]
        lines.append(f"{step['api_name']}: {step['status']} {step.get('message') or ''} {failed}")
    return "\n".join(lines)


def test_example_files_exist() -> None:
    assert [path.name for path in example_files()] == [
        "01-giris-ve-token.json",
        "02-lead-ve-teklif.json",
        "03-negatif-senaryolar.json",
    ]


def test_seed_is_idempotent(api: TestClient, admin, seeded) -> None:
    assert seeded["environment_created"] is True
    assert all(item["created"] for item in seeded["collections"])

    again = api.post("/api/collections/seed-demo", headers=admin).json()
    assert again["environment_created"] is False
    assert not any(item["created"] for item in again["collections"])

    env = api.get(f"/api/environments/{seeded['environment_id']}", headers=admin).json()
    values = {item["key"]: item["value"] for item in env["variables"]}
    assert values["demo_password"] == MASK  # şifre gizli değişken


def test_all_example_collections_pass(api: TestClient, admin, seeded, demo_network) -> None:
    env_id = seeded["environment_id"]
    results = {item["name"]: run(api, admin, item["id"], env_id) for item in seeded["collections"]}

    for name, result in results.items():
        assert result["status"] == "passed", f"{name}\n{explain(result)}"

    login_flow = results["Örnek 1 · Giriş ve token kontrolü"]
    assert login_flow["steps"][0]["extracted"][0] == {
        "variable": "token",
        "found": True,
        "value": MASK,
    }

    offer_flow = results["Örnek 2 · Lead ve teklif oluşturma"]
    assert offer_flow["passed_steps"] == 5
    extracted = {e["variable"] for e in offer_flow["steps"][1]["extracted"]}
    assert extracted == {"lead_id", "company_id"}

    negative = results["Örnek 3 · Negatif senaryolar"]
    assert negative["passed_steps"] == 8

    # Gizli değerler hiçbir sonuçta açık görünmüyor (rapor maskeleme)
    everything = json.dumps(results, ensure_ascii=False)
    assert "demo123" not in everything  # ortamdaki gizli şifre
    assert len([r for r in demo_network if r.url.path == "/auth/login"]) == 4


def test_examples_run_twice(api: TestClient, admin, seeded, demo_network) -> None:
    """Benzersiz e-posta ({{$uuid}}) sayesinde senaryolar tekrar tekrar çalıştırılabilir."""
    env_id = seeded["environment_id"]
    offer_flow = next(c for c in seeded["collections"] if c["name"].startswith("Örnek 2"))
    assert run(api, admin, offer_flow["id"], env_id)["status"] == "passed"
    assert run(api, admin, offer_flow["id"], env_id)["status"] == "passed"


def test_dashboard_reflects_runs(api: TestClient, admin, seeded, demo_network) -> None:
    env_id = seeded["environment_id"]
    for item in seeded["collections"]:
        run(api, admin, item["id"], env_id)

    totals = api.get("/api/dashboard", headers=admin).json()["totals"]
    assert totals["runs"] == 2 + 5 + 8
    assert totals["success_rate"] == 100.0
