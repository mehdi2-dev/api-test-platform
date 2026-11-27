"""API tanımları (ATOP-22..24, 26) testleri.

Gönderme testlerinde gerçek ağa çıkılmaz: httpx.MockTransport ile sahte bir sunucu
kurup giden isteği yakalıyoruz.
"""

import base64
import json
from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.inbound.http.apis import get_http_transport
from app.adapters.inbound.http.schemas.api_definition import MASK
from app.adapters.outbound.security.crypto import decrypt_json, encrypt_text
from app.domain.api_definitions import ApiDefinition
from app.domain.users import Role
from app.main import app

SECRET_TOKEN = "gizli-token-123"


@pytest.fixture
def tester(make_user, login) -> dict[str, str]:
    make_user("tester@apitest.com", Role.TESTER)
    return login("tester@apitest.com")


@pytest.fixture
def viewer(make_user, login) -> dict[str, str]:
    make_user("viewer@apitest.com", Role.VIEWER)
    return login("viewer@apitest.com")


def payload(**overrides) -> dict:
    data = {
        "name": "Kullanıcı listesi",
        "method": "POST",
        "url": "https://example.com/users",
        "headers": [{"key": "Accept", "value": "application/json"}],
        "query_params": [{"key": "page", "value": "1"}],
        "body_type": "json",
        "body": '{"ad": "Ayşe"}',
        "auth": {"type": "bearer", "token": SECRET_TOKEN},
    }
    data.update(overrides)
    return data


def create(api: TestClient, auth_headers: dict[str, str], **overrides) -> dict:
    """auth_headers: giriş yapan kullanıcının Authorization başlığı (API'nin header'ları değil)."""
    response = api.post("/api/apis", json=payload(**overrides), headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def captured() -> Iterator[list[httpx.Request]]:
    """Gönderilen istekleri biriktirir ve sabit bir JSON cevap döner."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 7, "durum": "oluşturuldu"})

    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(handler)
    yield requests
    app.dependency_overrides.pop(get_http_transport, None)


def use_transport(handler: Callable[[httpx.Request], httpx.Response]) -> None:
    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _clear_transport() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_http_transport, None)


# --- Oluşturma, şifreleme, maskeleme ---


def test_create_masks_secret_and_stores_it_encrypted(
    api: TestClient, tester, db_session: Session
) -> None:
    data = create(api, tester)

    assert data["auth"]["type"] == "bearer"
    assert data["auth"]["token"] == MASK
    assert SECRET_TOKEN not in json.dumps(data)

    row = db_session.get(ApiDefinition, data["id"])
    assert SECRET_TOKEN not in row.auth_config_encrypted
    assert decrypt_json(row.auth_config_encrypted) == {"token": SECRET_TOKEN}


def test_list_and_get_show_masked_secret(api: TestClient, tester, viewer) -> None:
    created = create(api, tester)

    listed = api.get("/api/apis", headers=viewer)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [created["id"]]

    detail = api.get(f"/api/apis/{created['id']}", headers=viewer).json()
    assert detail["auth"]["token"] == MASK
    assert detail["headers"] == [{"key": "Accept", "value": "application/json", "enabled": True}]


def test_search_by_name(api: TestClient, tester) -> None:
    create(api, tester, name="Sipariş oluştur")
    create(api, tester, name="Ürün listesi")

    names = [item["name"] for item in api.get("/api/apis?q=sipariş", headers=tester).json()]
    assert names == ["Sipariş oluştur"]


def test_basic_and_api_key_secrets_are_masked(api: TestClient, tester) -> None:
    basic = create(api, tester, auth={"type": "basic", "username": "ali", "password": "p@ss"})
    assert basic["auth"]["username"] == "ali"
    assert basic["auth"]["password"] == MASK

    key = create(
        api,
        tester,
        auth={"type": "api_key", "key_name": "X-API-Key", "key_value": "abc", "location": "query"},
    )
    assert key["auth"]["key_name"] == "X-API-Key"
    assert key["auth"]["key_value"] == MASK
    assert key["auth"]["location"] == "query"


# --- Doğrulama ---


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"body": '{"ad": "Ayşe",}'}, "JSON"),
        ({"url": "ftp://example.com"}, "http"),
        ({"auth": {"type": "bearer"}}, "token"),
        ({"auth": {"type": "basic", "username": "ali"}}, "password"),
        ({"auth": {"type": "api_key", "key_value": "x"}}, "key_name"),
        ({"method": "FETCH"}, "method"),
    ],
)
def test_invalid_input_returns_422(api: TestClient, tester, overrides, expected) -> None:
    response = api.post("/api/apis", json=payload(**overrides), headers=tester)
    assert response.status_code == 422
    assert expected in response.text


def test_mask_cannot_be_used_as_new_secret(api: TestClient, tester) -> None:
    response = api.post(
        "/api/apis", json=payload(auth={"type": "bearer", "token": MASK}), headers=tester
    )
    assert response.status_code == 422


def test_url_with_variable_is_accepted(api: TestClient, tester) -> None:
    data = create(api, tester, url="{{base_url}}/users")
    assert data["url"] == "{{base_url}}/users"


# --- Yetki ---


def test_requires_login(api: TestClient) -> None:
    assert api.get("/api/apis").status_code == 401


def test_viewer_cannot_change_anything(api: TestClient, tester, viewer) -> None:
    created = create(api, tester)
    api_id = created["id"]

    assert api.post("/api/apis", json=payload(), headers=viewer).status_code == 403
    assert api.patch(f"/api/apis/{api_id}", json={"name": "x"}, headers=viewer).status_code == 403
    assert api.delete(f"/api/apis/{api_id}", headers=viewer).status_code == 403
    assert api.post(f"/api/apis/{api_id}/send", headers=viewer).status_code == 403


# --- Güncelleme ve silme ---


def test_update_keeps_secret_when_mask_is_sent_back(
    api: TestClient, tester, db_session: Session
) -> None:
    created = create(api, tester)

    response = api.patch(
        f"/api/apis/{created['id']}",
        json={"name": "Yeni ad", "auth": created["auth"]},
        headers=tester,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Yeni ad"

    row = db_session.get(ApiDefinition, created["id"])
    assert decrypt_json(row.auth_config_encrypted) == {"token": SECRET_TOKEN}


def test_update_replaces_secret_and_can_remove_auth(
    api: TestClient, tester, db_session: Session
) -> None:
    created = create(api, tester)
    url = f"/api/apis/{created['id']}"

    api.patch(url, json={"auth": {"type": "bearer", "token": "yeni"}}, headers=tester)
    row = db_session.get(ApiDefinition, created["id"])
    assert decrypt_json(row.auth_config_encrypted) == {"token": "yeni"}

    response = api.patch(url, json={"auth": {"type": "none"}}, headers=tester)
    assert response.json()["auth"]["type"] == "none"
    assert db_session.get(ApiDefinition, created["id"]).auth_config_encrypted is None


def test_update_checks_body_against_existing_type(api: TestClient, tester) -> None:
    created = create(api, tester)  # body_type = json
    response = api.patch(f"/api/apis/{created['id']}", json={"body": "{bozuk"}, headers=tester)
    assert response.status_code == 422
    assert "JSON" in response.json()["detail"]


def test_delete_then_404(api: TestClient, tester) -> None:
    created = create(api, tester)
    url = f"/api/apis/{created['id']}"

    assert api.delete(url, headers=tester).status_code == 204
    assert api.get(url, headers=tester).status_code == 404
    assert api.delete(url, headers=tester).status_code == 404


# --- Gönderme ---


def test_send_builds_request_and_returns_response(api: TestClient, tester, captured) -> None:
    created = create(api, tester)

    response = api.post(f"/api/apis/{created['id']}/send", headers=tester)
    assert response.status_code == 200
    result = response.json()

    sent = captured[0]
    assert sent.method == "POST"
    assert str(sent.url) == "https://example.com/users?page=1"
    assert sent.headers["authorization"] == f"Bearer {SECRET_TOKEN}"
    assert sent.headers["accept"] == "application/json"
    assert sent.headers["content-type"] == "application/json"
    assert json.loads(sent.content) == {"ad": "Ayşe"}

    assert result["ok"] is True
    assert result["status_code"] == 201
    assert result["body_json"] == {"id": 7, "durum": "oluşturuldu"}
    assert result["elapsed_ms"] >= 0
    assert result["size_bytes"] > 0
    # Ekranda gösterilen istek özetinde token görünmemeli
    assert result["request"]["headers"]["Authorization"] == MASK
    assert SECRET_TOKEN not in response.text


def test_send_skips_disabled_rows(api: TestClient, tester, captured) -> None:
    created = create(
        api,
        tester,
        headers=[{"key": "X-Kapali", "value": "1", "enabled": False}],
        query_params=[{"key": "a", "value": "1"}, {"key": "b", "value": "2", "enabled": False}],
        auth={"type": "none"},
    )
    api.post(f"/api/apis/{created['id']}/send", headers=tester)

    assert str(captured[0].url) == "https://example.com/users?a=1"
    assert "x-kapali" not in captured[0].headers


def test_send_basic_auth(api: TestClient, tester, captured) -> None:
    created = create(api, tester, auth={"type": "basic", "username": "ali", "password": "p@ss"})
    api.post(f"/api/apis/{created['id']}/send", headers=tester)

    expected = base64.b64encode(b"ali:p@ss").decode()
    assert captured[0].headers["authorization"] == f"Basic {expected}"


def test_send_api_key_in_query_is_masked_in_summary(api: TestClient, tester, captured) -> None:
    created = create(
        api,
        tester,
        auth={"type": "api_key", "key_name": "api_key", "key_value": "s3cret", "location": "query"},
    )
    result = api.post(f"/api/apis/{created['id']}/send", headers=tester).json()

    assert captured[0].url.params["api_key"] == "s3cret"
    assert "s3cret" not in result["request"]["url"]
    assert "api_key=" in result["request"]["url"]


def test_send_api_key_in_header(api: TestClient, tester, captured) -> None:
    created = create(
        api, tester, auth={"type": "api_key", "key_name": "X-Token", "key_value": "s3cret"}
    )
    result = api.post(f"/api/apis/{created['id']}/send", headers=tester).json()

    assert captured[0].headers["x-token"] == "s3cret"
    assert result["request"]["headers"]["X-Token"] == MASK


def test_send_error_status_is_still_a_result(api: TestClient, tester) -> None:
    use_transport(lambda request: httpx.Response(500, text="Sunucu hatası"))
    created = create(api, tester)

    result = api.post(f"/api/apis/{created['id']}/send", headers=tester).json()
    assert result["ok"] is True
    assert result["status_code"] == 500
    assert result["body"] == "Sunucu hatası"
    assert result["body_json"] is None


def test_send_connection_error(api: TestClient, tester) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("bağlantı reddedildi", request=request)

    use_transport(handler)
    created = create(api, tester)

    result = api.post(f"/api/apis/{created['id']}/send", headers=tester).json()
    assert result["ok"] is False
    assert result["status_code"] is None
    assert "bağlanılamadı" in result["error"]


def test_send_with_unresolved_variable(api: TestClient, tester) -> None:
    created = create(api, tester, url="{{base_url}}/users")
    result = api.post(f"/api/apis/{created['id']}/send", headers=tester).json()

    assert result["ok"] is False
    assert "değişken" in result["error"]


def test_send_404(api: TestClient, tester) -> None:
    assert api.post("/api/apis/999/send", headers=tester).status_code == 404


# --- Şifreleme yardımcıları ---


def test_tampered_ciphertext_is_rejected() -> None:
    token = encrypt_text("merhaba")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(ValueError):
        decrypt_json(tampered)
