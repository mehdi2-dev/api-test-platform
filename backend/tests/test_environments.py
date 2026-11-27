"""Ortamlar, değişken çözümleme ve Production koruması (ATOP-27..30) testleri."""

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.apis import get_http_transport
from app.core.crypto import decrypt_text
from app.domain.testing.variables import find_variables, mask_secrets, resolve
from app.main import app
from app.models.environment import Environment
from app.models.user import Role
from app.schemas.api_definition import MASK

DEV_TOKEN = "dev-gizli-token-42"


@pytest.fixture
def tester(make_user, login) -> dict[str, str]:
    make_user("tester@apitest.com", Role.TESTER)
    return login("tester@apitest.com")


@pytest.fixture
def viewer(make_user, login) -> dict[str, str]:
    make_user("viewer@apitest.com", Role.VIEWER)
    return login("viewer@apitest.com")


@pytest.fixture
def captured() -> Iterator[list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(handler)
    yield requests
    app.dependency_overrides.pop(get_http_transport, None)


def make_env(api: TestClient, auth_headers: dict[str, str], **overrides) -> dict:
    data = {
        "name": "Dev",
        "description": "Geliştirme ortamı",
        "variables": [
            {"key": "base_url", "value": "https://dev.example.com"},
            {"key": "token", "value": DEV_TOKEN, "is_secret": True},
        ],
    }
    data.update(overrides)
    response = api.post("/api/environments", json=data, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


def make_api(api: TestClient, auth_headers: dict[str, str], **overrides) -> dict:
    data = {
        "name": "Kullanıcılar",
        "method": "GET",
        "url": "{{base_url}}/users",
        "auth": {"type": "bearer", "token": "{{token}}"},
    }
    data.update(overrides)
    response = api.post("/api/apis", json=data, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


def send(api: TestClient, auth_headers, api_id: int, **options) -> httpx.Response:
    return api.post(f"/api/apis/{api_id}/send", json=options, headers=auth_headers)


# --- Değişken çözümleme motoru (saf fonksiyonlar) ---


def test_resolve_replaces_known_and_reports_missing() -> None:
    missing: set[str] = set()
    text = resolve(
        "{{base_url}}/u/{{ id }}?k={{yok}}", {"base_url": "https://x", "id": "7"}, missing
    )
    assert text == "https://x/u/7?k={{yok}}"
    assert missing == {"yok"}


def test_find_variables_and_mask() -> None:
    assert find_variables("{{a}} ve {{b.c}} ve {a}") == {"a", "b.c"}
    assert mask_secrets("https://x?k=s3 cret&t=s3cret", ["s3 cret", "s3cret"]) == (
        f"https://x?k={MASK}&t={MASK}"
    )


# --- Ortam CRUD ---


def test_create_environment_masks_and_encrypts_secret(
    api: TestClient, tester, db_session: Session
) -> None:
    env = make_env(api, tester)

    variables = {item["key"]: item for item in env["variables"]}
    assert variables["base_url"]["value"] == "https://dev.example.com"
    assert variables["token"] == {"key": "token", "value": MASK, "is_secret": True}

    stored = {v.key: v for v in db_session.get(Environment, env["id"]).variables}
    assert DEV_TOKEN not in stored["token"].value
    assert decrypt_text(stored["token"].value) == DEV_TOKEN


def test_duplicate_environment_name_is_409(api: TestClient, tester) -> None:
    make_env(api, tester)
    response = api.post("/api/environments", json={"name": "Dev"}, headers=tester)
    assert response.status_code == 409


@pytest.mark.parametrize(
    "variables",
    [
        [{"key": "a", "value": "1"}, {"key": "a", "value": "2"}],
        [{"key": "1sayi", "value": "x"}],
        [{"key": "bosluk var", "value": "x"}],
    ],
)
def test_invalid_variables_are_422(api: TestClient, tester, variables) -> None:
    response = api.post(
        "/api/environments", json={"name": "X", "variables": variables}, headers=tester
    )
    assert response.status_code == 422


def test_update_keeps_secret_and_replaces_list(
    api: TestClient, tester, db_session: Session
) -> None:
    env = make_env(api, tester)
    url = f"/api/environments/{env['id']}"

    # Arayüzün yaptığı gibi: maskeli değeri geri gönder, bir değişken ekle, base_url'i değiştir
    response = api.patch(
        url,
        json={
            "variables": [
                {"key": "base_url", "value": "https://dev2.example.com"},
                {"key": "token", "value": MASK, "is_secret": True},
                {"key": "user_id", "value": "5"},
            ]
        },
        headers=tester,
    )
    assert response.status_code == 200, response.text
    keys = [item["key"] for item in response.json()["variables"]]
    assert keys == ["base_url", "token", "user_id"]

    db_session.expire_all()
    stored = {v.key: v for v in db_session.get(Environment, env["id"]).variables}
    assert decrypt_text(stored["token"].value) == DEV_TOKEN
    assert stored["base_url"].value == "https://dev2.example.com"

    # Listeden çıkarılan değişken silinir
    response = api.patch(
        url, json={"variables": [{"key": "base_url", "value": "x"}]}, headers=tester
    )
    assert [item["key"] for item in response.json()["variables"]] == ["base_url"]


def test_mask_without_saved_secret_is_422(api: TestClient, tester) -> None:
    env = make_env(api, tester)
    response = api.patch(
        f"/api/environments/{env['id']}",
        json={"variables": [{"key": "yeni", "value": MASK, "is_secret": True}]},
        headers=tester,
    )
    assert response.status_code == 422


def test_viewer_can_read_but_not_write(api: TestClient, tester, viewer) -> None:
    env = make_env(api, tester)
    url = f"/api/environments/{env['id']}"

    assert api.get("/api/environments", headers=viewer).status_code == 200
    assert api.get(url, headers=viewer).json()["variables"][1]["value"] == MASK
    assert api.post("/api/environments", json={"name": "Y"}, headers=viewer).status_code == 403
    assert api.patch(url, json={"name": "Z"}, headers=viewer).status_code == 403
    assert api.delete(url, headers=viewer).status_code == 403


def test_delete_environment(api: TestClient, tester) -> None:
    env = make_env(api, tester)
    url = f"/api/environments/{env['id']}"
    assert api.delete(url, headers=tester).status_code == 204
    assert api.get(url, headers=tester).status_code == 404


# --- Ortamla gönderme ---


def test_send_resolves_variables_from_environment(api: TestClient, tester, captured) -> None:
    env = make_env(api, tester)
    definition = make_api(
        api,
        tester,
        headers=[{"key": "X-Ortam", "value": "{{env_name}}"}],
        query_params=[{"key": "t", "value": "{{token}}"}],
    )
    api.patch(
        f"/api/environments/{env['id']}",
        json={
            "variables": [
                {"key": "base_url", "value": "https://dev.example.com"},
                {"key": "token", "value": MASK, "is_secret": True},
                {"key": "env_name", "value": "dev"},
            ]
        },
        headers=tester,
    )

    response = send(api, tester, definition["id"], environment_id=env["id"])
    assert response.status_code == 200, response.text
    result = response.json()

    sent = captured[0]
    assert str(sent.url) == f"https://dev.example.com/users?t={DEV_TOKEN}"
    assert sent.headers["authorization"] == f"Bearer {DEV_TOKEN}"
    assert sent.headers["x-ortam"] == "dev"

    assert result["ok"] is True
    assert result["environment"] == "Dev"
    # Gizli değişkenin değeri ekrana giden özetin hiçbir yerinde görünmemeli
    assert DEV_TOKEN not in response.text
    assert result["request"]["url"] == f"https://dev.example.com/users?t={MASK}"


def test_same_api_different_environments(api: TestClient, tester, captured) -> None:
    dev = make_env(api, tester)
    stage = make_env(
        api,
        tester,
        name="Stage",
        variables=[
            {"key": "base_url", "value": "https://stage.example.com"},
            {"key": "token", "value": "stage-token", "is_secret": True},
        ],
    )
    definition = make_api(api, tester)

    send(api, tester, definition["id"], environment_id=dev["id"])
    send(api, tester, definition["id"], environment_id=stage["id"])

    assert [request.url.host for request in captured] == ["dev.example.com", "stage.example.com"]


def test_missing_variable_returns_error_without_sending(api: TestClient, tester, captured) -> None:
    env = make_env(api, tester, variables=[{"key": "base_url", "value": "https://x.com"}])
    definition = make_api(api, tester)

    result = send(api, tester, definition["id"], environment_id=env["id"]).json()
    assert result["ok"] is False
    assert "token" in result["error"]
    assert captured == []


def test_send_without_environment_asks_for_one(api: TestClient, tester) -> None:
    definition = make_api(api, tester)
    result = api.post(f"/api/apis/{definition['id']}/send", headers=tester).json()
    assert result["ok"] is False
    assert "ortam seçin" in result["error"].lower()


def test_send_with_unknown_environment_is_404(api: TestClient, tester) -> None:
    definition = make_api(api, tester)
    assert send(api, tester, definition["id"], environment_id=999).status_code == 404


# --- Production koruması ---


@pytest.fixture
def prod(api: TestClient, tester) -> dict:
    return make_env(
        api,
        tester,
        name="Prod",
        is_production=True,
        variables=[
            {"key": "base_url", "value": "https://api.example.com"},
            {"key": "token", "value": "prod-token", "is_secret": True},
        ],
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_request_on_production_needs_confirmation(
    api: TestClient, tester, prod, captured, method
) -> None:
    definition = make_api(api, tester, method=method)

    response = send(api, tester, definition["id"], environment_id=prod["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "production_confirmation_required"
    assert captured == []

    response = send(
        api, tester, definition["id"], environment_id=prod["id"], confirm_production=True
    )
    assert response.status_code == 200
    assert len(captured) == 1


def test_read_request_on_production_needs_no_confirmation(
    api: TestClient, tester, prod, captured
) -> None:
    definition = make_api(api, tester, method="GET")
    response = send(api, tester, definition["id"], environment_id=prod["id"])
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_mutating_request_on_non_production_runs_directly(
    api: TestClient, tester, captured
) -> None:
    env = make_env(api, tester)
    definition = make_api(api, tester, method="DELETE")
    response = send(api, tester, definition["id"], environment_id=env["id"])
    assert response.status_code == 200
    assert len(captured) == 1
