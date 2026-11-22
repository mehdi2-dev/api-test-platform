"""Demo CRM servisinin kendisi doğru davranıyor mu? (ATOP-52)"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.demo.main import app as demo_app
from app.demo.main import store


@pytest.fixture
def demo() -> Iterator[TestClient]:
    store.reset()
    yield TestClient(demo_app)
    store.reset()


def token(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": "demo", "password": "demo123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login(demo: TestClient) -> None:
    assert demo.post("/auth/login", json={"username": "demo", "password": "x"}).status_code == 401
    assert token(demo)["Authorization"].startswith("Bearer ")


def test_requires_token(demo: TestClient) -> None:
    assert demo.get("/companies").status_code == 401
    assert demo.get("/companies", headers={"Authorization": "Bearer uydurma"}).status_code == 401
    assert len(demo.get("/companies", headers=token(demo)).json()) == 3


def test_lead_offer_flow(demo: TestClient) -> None:
    headers = token(demo)
    lead = demo.post(
        "/leads",
        json={"company_id": 2, "contact_name": "Ayşe", "email": "Ayse@Demo-Firma.com"},
        headers=headers,
    )
    assert lead.status_code == 201
    assert lead.json()["email"] == "ayse@demo-firma.com"

    duplicate = demo.post(
        "/leads",
        json={"company_id": 2, "contact_name": "Ayşe", "email": "ayse@demo-firma.com"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    # lead_id metin olarak gelse de kabul edilir ({{lead_id}} değişkeni JSON'da tırnak içinde)
    offer = demo.post(
        "/offers", json={"lead_id": str(lead.json()["id"]), "amount": 100}, headers=headers
    )
    assert offer.status_code == 201
    assert demo.get(f"/leads/{lead.json()['id']}", headers=headers).json()["status"] == "offered"
    offers = demo.get("/companies/2/offers", headers=headers).json()
    assert [item["id"] for item in offers] == [offer.json()["id"]]

    assert (
        demo.post("/offers", json={"lead_id": 1, "amount": -5}, headers=headers).status_code == 422
    )
    assert demo.get("/leads/999", headers=headers).status_code == 404
