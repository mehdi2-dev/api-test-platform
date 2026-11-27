"""Koleksiyonlar (ATOP-37..40) testleri.

Sahte sunucu küçük bir "giriş yap -> token al -> korumalı kaynağı çek" akışı canlandırır:
    POST /login      -> {"access_token": "t-123", "user": {"id": 7}}
    GET  /me         -> Authorization: Bearer t-123 ise 200, değilse 401
    GET  /users/7    -> 200 {"id": 7}
"""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.inbound.http.apis import get_http_transport
from app.adapters.inbound.http.schemas.api_definition import MASK, SendResult, SentRequest
from app.adapters.inbound.http.schemas.collection import Extraction
from app.adapters.outbound.security.crypto import decrypt_json
from app.composition import extract_value
from app.domain.api_definitions import ApiDefinition
from app.domain.users import Role
from app.main import app

TOKEN = "t-123"


def fake_server(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/login":
        return httpx.Response(200, json={"access_token": TOKEN, "user": {"id": 7}})
    if path == "/me":
        if request.headers.get("authorization") == f"Bearer {TOKEN}":
            return httpx.Response(200, json={"email": "ayse@example.com"})
        return httpx.Response(401, json={"detail": "yetkisiz"})
    if path == "/users/7":
        return httpx.Response(200, json={"id": 7})
    return httpx.Response(404, json={"detail": "yok"})


@pytest.fixture
def server() -> Iterator[list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return fake_server(request)

    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(handler)
    yield requests
    app.dependency_overrides.pop(get_http_transport, None)


@pytest.fixture
def tester(make_user, login) -> dict[str, str]:
    make_user("tester@apitest.com", Role.TESTER)
    return login("tester@apitest.com")


@pytest.fixture
def viewer(make_user, login) -> dict[str, str]:
    make_user("viewer@apitest.com", Role.VIEWER)
    return login("viewer@apitest.com")


def make_api(api: TestClient, headers, name: str, method: str, url: str, **extra) -> int:
    data = {
        "name": name,
        "method": method,
        "url": url,
        "assertions": [{"type": "status_code", "operator": "equals", "expected": "200"}],
    } | extra
    response = api.post("/api/apis", json=data, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def flow(api: TestClient, tester) -> dict[str, int]:
    """Giriş -> profil -> kullanıcı akışı için üç API tanımı."""
    return {
        "login": make_api(api, tester, "Giriş", "POST", "https://srv.test/login"),
        "me": make_api(
            api,
            tester,
            "Profil",
            "GET",
            "https://srv.test/me",
            auth={"type": "bearer", "token": "{{token}}"},
        ),
        "user": make_api(api, tester, "Kullanıcı", "GET", "https://srv.test/users/{{user_id}}"),
    }


def steps(flow: dict[str, int]) -> list[dict]:
    return [
        {
            "api_definition_id": flow["login"],
            "extractions": [
                {"variable": "token", "path": "$.access_token", "secret": True},
                {"variable": "user_id", "path": "$.user.id"},
            ],
        },
        {"api_definition_id": flow["me"]},
        {"api_definition_id": flow["user"]},
    ]


def make_collection(api: TestClient, headers, flow, **extra) -> dict:
    data = {"name": "Giriş akışı", "items": steps(flow)} | extra
    response = api.post("/api/collections", json=data, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def run(api: TestClient, headers, collection_id: int, **options) -> httpx.Response:
    return api.post(f"/api/collections/{collection_id}/run", json=options, headers=headers)


# --- CRUD ve sıralama (ATOP-37) ---


def test_create_collection_keeps_order(api: TestClient, tester, flow) -> None:
    data = make_collection(api, tester, flow)
    assert [item["api_name"] for item in data["items"]] == ["Giriş", "Profil", "Kullanıcı"]
    assert [item["position"] for item in data["items"]] == [0, 1, 2]
    assert data["items"][0]["extractions"][0]["variable"] == "token"


def test_reorder_and_remove_steps(api: TestClient, tester, flow) -> None:
    data = make_collection(api, tester, flow)
    reordered = [steps(flow)[2], steps(flow)[0]]

    response = api.patch(
        f"/api/collections/{data['id']}", json={"items": reordered}, headers=tester
    )
    assert response.status_code == 200, response.text
    assert [item["api_name"] for item in response.json()["items"]] == ["Kullanıcı", "Giriş"]


def test_same_api_can_appear_twice(api: TestClient, tester, flow) -> None:
    items = [{"api_definition_id": flow["login"]}, {"api_definition_id": flow["login"]}]
    response = api.post(
        "/api/collections", json={"name": "İki kez", "items": items}, headers=tester
    )
    assert response.status_code == 201
    assert len(response.json()["items"]) == 2


def test_unknown_api_and_duplicate_name(api: TestClient, tester, flow) -> None:
    bad = {"name": "X", "items": [{"api_definition_id": 999}]}
    assert api.post("/api/collections", json=bad, headers=tester).status_code == 422

    make_collection(api, tester, flow)
    duplicate = api.post("/api/collections", json={"name": "Giriş akışı"}, headers=tester)
    assert duplicate.status_code == 409


@pytest.mark.parametrize(
    "extraction",
    [
        {"variable": "1sayi", "path": "$.a"},
        {"variable": "token"},  # json_path için yol gerekli
        {"variable": "token", "path": "$..a"},
        {"variable": "token", "source": "body", "path": "$.a"},
    ],
)
def test_invalid_extraction_is_422(api: TestClient, tester, flow, extraction) -> None:
    items = [{"api_definition_id": flow["login"], "extractions": [extraction]}]
    response = api.post("/api/collections", json={"name": "X", "items": items}, headers=tester)
    assert response.status_code == 422


def test_list_get_delete(api: TestClient, tester, viewer, flow) -> None:
    data = make_collection(api, tester, flow)

    listed = api.get("/api/collections", headers=viewer).json()
    assert listed[0]["item_count"] == 3
    assert listed[0]["last_run_status"] is None
    assert api.get(f"/api/collections/{data['id']}", headers=viewer).status_code == 200

    assert api.delete(f"/api/collections/{data['id']}", headers=tester).status_code == 204
    assert api.get(f"/api/collections/{data['id']}", headers=tester).status_code == 404
    # API tanımları silinmez
    assert api.get(f"/api/apis/{flow['login']}", headers=tester).status_code == 200


def test_viewer_cannot_change_or_run(api: TestClient, tester, viewer, flow) -> None:
    data = make_collection(api, tester, flow)
    url = f"/api/collections/{data['id']}"
    assert api.post("/api/collections", json={"name": "Y"}, headers=viewer).status_code == 403
    assert api.patch(url, json={"name": "Z"}, headers=viewer).status_code == 403
    assert api.delete(url, headers=viewer).status_code == 403
    assert run(api, viewer, data["id"]).status_code == 403


# --- Değişken çıkarma (ATOP-38) ---


def _result(body, headers=None, status_code=200) -> SendResult:
    return SendResult(
        ok=True,
        status_code=status_code,
        elapsed_ms=1,
        headers=headers or {},
        body=json.dumps(body),
        body_json=body,
        request=SentRequest(method="GET", url="https://x", headers={}),
    )


def test_extract_value_sources() -> None:
    result = _result({"a": {"b": [10, "x"]}, "s": "metin"}, {"Location": "/users/9"}, 201)

    def get(**data) -> str | None:
        return extract_value(Extraction(variable="v", **data), result)

    assert get(path="$.s") == "metin"
    assert get(path="$.a.b[0]") == "10"
    assert get(path="$.a") == '{"b": [10, "x"]}'
    assert get(path="$.yok") is None
    assert get(source="header", path="location") == "/users/9"
    assert get(source="status_code") == "201"


# --- Çalıştırma (ATOP-39) ---


def test_run_passes_token_between_steps(api: TestClient, tester, flow, server) -> None:
    data = make_collection(api, tester, flow)

    response = run(api, tester, data["id"])
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["status"] == "passed"
    assert (result["total_steps"], result["passed_steps"]) == (3, 3)
    # 2. adım, 1. adımın cevabındaki token ile gitti; 3. adım user_id ile
    assert server[1].headers["authorization"] == f"Bearer {TOKEN}"
    assert server[2].url.path == "/users/7"

    first = result["steps"][0]
    extracted = {item["variable"]: item for item in first["extracted"]}
    assert extracted["token"] == {"variable": "token", "found": True, "value": MASK}
    assert extracted["user_id"]["value"] == "7"

    # Gizli değişkenin değeri hiçbir yerde açık görünmemeli (2. adımın istek özeti dahil)
    me_run = result["step_runs"][str(result["steps"][1]["test_run_id"])]
    assert me_run["request"]["headers"]["Authorization"] == MASK
    assert TOKEN not in json.dumps(
        {key: value for key, value in result.items() if key != "step_runs"}
    )


def test_missing_extraction_fails_step_and_continues(api: TestClient, tester, flow, server) -> None:
    items = steps(flow)
    items[0]["extractions"][0]["path"] = "$.yanlis_alan"
    data = make_collection(api, tester, flow, items=items)

    result = run(api, tester, data["id"]).json()
    statuses = [step["status"] for step in result["steps"]]
    # Token alınamadı -> 1. adım kaldı; 2. adım {{token}} çözülemediği için hata;
    # stop_on_failure kapalı olduğundan 3. adım yine çalıştı
    assert statuses == ["failed", "error", "passed"]
    assert result["status"] == "failed"
    assert result["steps"][0]["extracted"][0]["found"] is False


def test_stop_on_failure_skips_remaining(api: TestClient, tester, flow, server) -> None:
    items = steps(flow)
    items[0]["extractions"][0]["path"] = "$.yanlis_alan"
    data = make_collection(api, tester, flow, items=items, stop_on_failure=True)

    result = run(api, tester, data["id"]).json()
    assert [step["status"] for step in result["steps"]] == ["failed", "skipped", "skipped"]
    assert result["skipped_steps"] == 2
    assert len(server) == 1  # sadece ilk istek gitti


def test_disabled_steps_are_not_run(api: TestClient, tester, flow, server) -> None:
    items = steps(flow)
    items[2]["enabled"] = False
    data = make_collection(api, tester, flow, items=items)

    result = run(api, tester, data["id"]).json()
    assert result["total_steps"] == 2
    assert len(server) == 2


def test_run_history(api: TestClient, tester, flow, server) -> None:
    data = make_collection(api, tester, flow)
    first = run(api, tester, data["id"]).json()

    runs = api.get(f"/api/collections/{data['id']}/runs", headers=tester).json()
    assert [item["id"] for item in runs] == [first["id"]]
    detail = api.get(f"/api/collections/{data['id']}/runs/{first['id']}", headers=tester)
    assert detail.status_code == 200
    assert len(detail.json()["step_runs"]) == 3
    listed = api.get("/api/collections", headers=tester).json()
    assert listed[0]["last_run_status"] == "passed"

    # Adımlar API'nin kendi çalıştırma geçmişinde de görünür
    api_runs = api.get(f"/api/runs?api_id={flow['login']}", headers=tester).json()
    assert api_runs[0]["collection_run_id"] == first["id"]


def test_empty_collection_cannot_run(api: TestClient, tester) -> None:
    data = api.post("/api/collections", json={"name": "Boş"}, headers=tester).json()
    assert run(api, tester, data["id"]).status_code == 422


def test_production_needs_confirmation(api: TestClient, tester, flow, server) -> None:
    prod = api.post(
        "/api/environments", json={"name": "Prod", "is_production": True}, headers=tester
    ).json()
    data = make_collection(api, tester, flow)  # ilk adım POST

    response = run(api, tester, data["id"], environment_id=prod["id"])
    assert response.status_code == 409
    assert "POST Giriş" in response.json()["detail"]["message"]
    assert server == []

    confirmed = run(api, tester, data["id"], environment_id=prod["id"], confirm_production=True)
    assert confirmed.status_code == 200
    assert confirmed.json()["environment_name"] == "Prod"


# --- İçe / dışa aktarma (ATOP-40) ---


def test_export_hides_secrets(api: TestClient, tester, flow) -> None:
    secret_api = make_api(
        api,
        tester,
        "Gizli",
        "GET",
        "{{base_url}}/gizli",
        auth={"type": "bearer", "token": "cok-gizli-deger"},
    )
    items = [*steps(flow), {"api_definition_id": secret_api}]
    data = make_collection(api, tester, flow, items=items)

    response = api.get(f"/api/collections/{data['id']}/export", headers=tester)
    assert response.status_code == 200
    exported = response.json()

    assert "cok-gizli-deger" not in response.text
    assert exported["format"] == "api-test-platform/collection"
    assert len(exported["apis"]) == 4
    assert exported["apis"][3]["auth"]["token"] == "{{token}}"
    # token ve user_id adımlarda üretildiği için ortamda gerekmez; base_url gerekir
    assert exported["required_variables"] == ["base_url"]


def test_import_creates_apis_and_collection(
    api: TestClient, tester, flow, server, db_session: Session
) -> None:
    data = make_collection(api, tester, flow)
    exported = api.get(f"/api/collections/{data['id']}/export", headers=tester).json()

    response = api.post("/api/collections/import", json=exported, headers=tester)
    assert response.status_code == 201, response.text
    imported = response.json()
    assert imported["collection"]["name"] == "Giriş akışı (2)"
    assert imported["created_apis"] == 3

    new_ids = [item["api_definition_id"] for item in imported["collection"]["items"]]
    assert set(new_ids).isdisjoint(flow.values())
    me = db_session.get(ApiDefinition, new_ids[1])
    assert decrypt_json(me.auth_config_encrypted) == {"token": "{{token}}"}

    # İçe aktarılan koleksiyon aynı şekilde çalışır
    result = run(api, tester, imported["collection"]["id"]).json()
    assert result["status"] == "passed"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "X", "format": "baska-format"},
        {"name": "X", "apis": [], "steps": [{"api": 0}]},
        {
            "name": "X",
            "apis": [{"name": "A", "method": "GET", "url": "ftp://x"}],
            "steps": [{"api": 0}],
        },
    ],
)
def test_import_rejects_invalid_files(api: TestClient, tester, payload) -> None:
    assert api.post("/api/collections/import", json=payload, headers=tester).status_code == 422
