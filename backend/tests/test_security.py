"""Güvenlik testleri (ATOP-49..51).

1. Yetki matrisi: her endpoint için hangi rolün erişebildiği tek tabloda
2. Giriş yapmadan hiçbir korumalı endpoint'e erişilemiyor (tüm route'lar otomatik taranır)
3. Giriş denemesi sınırı, güvenlik başlıkları
4. Maskeleme: saklanan cevaplar, kural sonuçları, loglar
5. Şifreleme anahtarı rotasyonu ve güvenlik ayarı uyarıları
"""

import base64
import json
import logging
import re
from collections.abc import Iterator

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.inbound.http.apis import get_http_transport
from app.adapters.inbound.http.schemas.api_definition import MASK
from app.adapters.outbound.security import crypto
from app.cli import rotate_all
from app.core.config import settings
from app.core.logging import SensitiveDataFilter, mask_log_text
from app.domain.api_definitions import ApiDefinition, AuthType, HttpMethod
from app.domain.users import Role
from app.main import app, check_security_settings

ALL = {"viewer", "tester", "admin"}
EDITORS = {"tester", "admin"}
ADMIN = {"admin"}

# (metod, adres, erişebilen roller)
MATRIX = [
    ("GET", "/api/auth/me", ALL),
    ("GET", "/api/users", ADMIN),
    ("POST", "/api/users", ADMIN),
    ("GET", "/api/users/1", ADMIN),
    ("PATCH", "/api/users/1", ADMIN),
    ("GET", "/api/apis", ALL),
    ("POST", "/api/apis", EDITORS),
    ("GET", "/api/apis/1", ALL),
    ("PATCH", "/api/apis/1", EDITORS),
    ("DELETE", "/api/apis/1", EDITORS),
    ("POST", "/api/apis/1/send", EDITORS),
    ("POST", "/api/apis/1/run", EDITORS),
    ("GET", "/api/environments", ALL),
    ("POST", "/api/environments", EDITORS),
    ("GET", "/api/environments/1", ALL),
    ("PATCH", "/api/environments/1", EDITORS),
    ("DELETE", "/api/environments/1", EDITORS),
    ("GET", "/api/runs", ALL),
    ("GET", "/api/runs/history", ALL),
    ("GET", "/api/runs/1", ALL),
    ("GET", "/api/runs/1/baseline", ALL),
    ("GET", "/api/collections", ALL),
    ("POST", "/api/collections", EDITORS),
    ("POST", "/api/collections/import", EDITORS),
    ("POST", "/api/collections/seed-demo", ADMIN),
    ("GET", "/api/collections/1", ALL),
    ("PATCH", "/api/collections/1", EDITORS),
    ("DELETE", "/api/collections/1", EDITORS),
    ("GET", "/api/collections/1/export", ALL),
    ("POST", "/api/collections/1/run", EDITORS),
    ("POST", "/api/collections/1/run-async", EDITORS),
    ("GET", "/api/collections/1/runs", ALL),
    ("GET", "/api/collections/1/runs/1", ALL),
    ("GET", "/api/schedules", ALL),
    ("GET", "/api/schedules/preview?cron=@daily", ALL),
    ("POST", "/api/schedules", EDITORS),
    ("PATCH", "/api/schedules/1", EDITORS),
    ("DELETE", "/api/schedules/1", EDITORS),
    ("POST", "/api/schedules/1/run-now", EDITORS),
    ("GET", "/api/dashboard", ALL),
    ("GET", "/api/notifications", EDITORS),
    ("POST", "/api/notifications", ADMIN),
    ("PATCH", "/api/notifications/1", ADMIN),
    ("DELETE", "/api/notifications/1", ADMIN),
    ("POST", "/api/notifications/1/test", ADMIN),
]

PUBLIC = {("GET", "/api/health"), ("POST", "/api/auth/login"), ("POST", "/api/auth/refresh")}


@pytest.fixture
def role_headers(make_user, login) -> dict[str, dict[str, str]]:
    headers = {}
    for role in Role:
        email = f"{role.value}@apitest.com"
        make_user(email, role)
        headers[role.value] = login(email)
    return headers


def call(api: TestClient, method: str, path: str, headers=None) -> httpx.Response:
    body = None if method in ("GET", "DELETE") else {}
    return api.request(method, path, json=body, headers=headers or {})


# --- 1. Yetki matrisi (ATOP-51) ---


def test_role_matrix(api: TestClient, role_headers) -> None:
    """Her satır için üç rolün hepsi denenir; hatalar tek seferde listelenir."""
    problems = []
    for method, path, allowed in MATRIX:
        for role in ("viewer", "tester", "admin"):
            code = call(api, method, path, role_headers[role]).status_code
            if role in allowed and code in (401, 403):
                problems.append(f"{role} {method} {path}: izinli olmalıydı, {code} döndü")
            if role not in allowed and code != 403:
                problems.append(f"{role} {method} {path}: 403 bekleniyordu, {code} döndü")
    assert problems == []


def test_matrix_covers_every_protected_route() -> None:
    """Yeni bir endpoint eklenip matrise yazılmazsa bu test hatırlatır."""
    listed = {(method, re.sub(r"\?.*$", "", path)) for method, path, _ in MATRIX}
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api"):
            continue
        for method in route.methods:
            concrete = re.sub(r"\{[^}]+\}", "1", route.path)
            if (method, concrete) not in listed and (method, route.path) not in PUBLIC:
                missing.append(f"{method} {route.path}")
    assert missing == [], f"Yetki matrisinde olmayan endpoint'ler: {missing}"


def test_every_protected_route_requires_login(api: TestClient, db_session) -> None:
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api"):
            continue
        for method in route.methods:
            if (method, route.path) in PUBLIC:
                continue
            path = re.sub(r"\{[^}]+\}", "1", route.path)
            response = call(api, method, path)
            assert response.status_code == 401, f"{method} {route.path} giriş istemiyor!"


def test_tampered_token_is_rejected(api: TestClient, role_headers) -> None:
    token = role_headers["viewer"]["Authorization"].split()[1]
    header, _, signature = token.split(".")
    # Rolü admin yapmaya çalışan saldırgan: imza tutmaz
    forged = json.dumps({"sub": "1", "role": "admin", "type": "access", "exp": 9999999999})
    fake_payload = base64.urlsafe_b64encode(forged.encode()).decode().rstrip("=")
    response = api.get(
        "/api/users", headers={"Authorization": f"Bearer {header}.{fake_payload}.{signature}"}
    )
    assert response.status_code == 401


# --- 2. Giriş denemesi sınırı ve başlıklar ---


def test_login_is_locked_after_too_many_failures(api: TestClient, make_user) -> None:
    make_user("hedef@apitest.com")
    wrong = {"email": "hedef@apitest.com", "password": "YanlisSifre"}
    for _ in range(settings.login_max_attempts):
        assert api.post("/api/auth/login", json=wrong).status_code == 401

    blocked = api.post(
        "/api/auth/login", json={"email": "hedef@apitest.com", "password": "Sifre12345"}
    )
    assert blocked.status_code == 429  # doğru şifre bile kilit süresince kabul edilmez
    assert int(blocked.headers["Retry-After"]) > 0

    # Başka bir hesap etkilenmez
    make_user("baska@apitest.com")
    other = {"email": "baska@apitest.com", "password": "Sifre12345"}
    assert api.post("/api/auth/login", json=other).status_code == 200


def test_successful_login_resets_counter(api: TestClient, make_user) -> None:
    make_user("hedef@apitest.com")
    wrong = {"email": "hedef@apitest.com", "password": "YanlisSifre"}
    right = {"email": "hedef@apitest.com", "password": "Sifre12345"}
    for _ in range(settings.login_max_attempts - 1):
        api.post("/api/auth/login", json=wrong)
    assert api.post("/api/auth/login", json=right).status_code == 200
    for _ in range(settings.login_max_attempts - 1):
        assert api.post("/api/auth/login", json=wrong).status_code == 401


def test_security_headers(api: TestClient, db_session) -> None:
    response = api.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


# --- 3. Maskeleme (ATOP-50) ---


@pytest.fixture
def echo_server() -> Iterator[None]:
    """Gelen Authorization header'ını ve sabit bir token'ı cevapta geri döndürür."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "cevaptaki-gizli-token",
                "token_type": "bearer",
                "echo": request.headers.get("authorization", ""),
                "user": {"name": "Ayşe", "password": "duz-sifre"},
            },
            headers={"Set-Cookie": "session=abc123"},
        )

    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(handler)
    yield
    app.dependency_overrides.pop(get_http_transport, None)


def test_stored_run_masks_tokens_and_secrets(api: TestClient, role_headers, echo_server) -> None:
    tester = role_headers["tester"]
    env = api.post(
        "/api/environments",
        json={
            "name": "Dev",
            "variables": [{"key": "token", "value": "ortam-gizli-degeri", "is_secret": True}],
        },
        headers=tester,
    ).json()
    created = api.post(
        "/api/apis",
        json={
            "name": "Giriş",
            "url": "https://srv.test/login",
            "auth": {"type": "bearer", "token": "{{token}}"},
            "assertions": [
                {"type": "json_path", "target": "$.access_token", "operator": "exists"},
                {
                    "type": "json_path",
                    "target": "$.user.name",
                    "operator": "equals",
                    "expected": "Ayşe",
                },
            ],
        },
        headers=tester,
    ).json()

    run = api.post(
        f"/api/apis/{created['id']}/run", json={"environment_id": env["id"]}, headers=tester
    ).json()
    # Kurallar maskelenmemiş gerçek cevapla çalıştı
    assert run["status"] == "passed"

    detail = api.get(f"/api/runs/{run['id']}", headers=tester)
    text = detail.text
    for secret in ("cevaptaki-gizli-token", "ortam-gizli-degeri", "duz-sifre", "abc123"):
        assert secret not in text, secret
    data = detail.json()
    body = json.loads(data["response"]["body"])
    assert body["access_token"] == MASK
    assert body["user"] == {"name": "Ayşe", "password": MASK}
    assert data["response"]["headers"]["set-cookie"] == MASK
    assert data["assertion_results"][0]["actual"] == MASK  # $.access_token
    assert data["assertion_results"][1]["actual"] == "Ayşe"  # hassas olmayan alan


def test_send_preview_is_masked_too(api: TestClient, role_headers, echo_server) -> None:
    tester = role_headers["tester"]
    created = api.post(
        "/api/apis", json={"name": "Giriş", "url": "https://srv.test/login"}, headers=tester
    ).json()
    result = api.post(f"/api/apis/{created['id']}/send", headers=tester)
    assert "cevaptaki-gizli-token" not in result.text
    assert result.json()["body_json"]["access_token"] == MASK


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("Authorization: Bearer eyJhbGciOi.abc.def", "Authorization: Bearer ********"),
        (
            "GET https://x.com/a?api_key=s3cret&page=1",
            "GET https://x.com/a?api_key=********&page=1",
        ),
        (
            '{"password": "Admin12345", "email": "a@b.c"}',
            '{"password": "********", "email": "a@b.c"}',
        ),
        ("Basic YWxpOnBAc3M=", "Basic ********"),
        ("normal bir log satırı", "normal bir log satırı"),
    ],
)
def test_log_masking(raw, masked) -> None:
    assert mask_log_text(raw) == masked


def test_log_filter_masks_formatted_arguments() -> None:
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "İstek gönderildi: %s", ("Bearer gizli.jwt.token",), None
    )
    SensitiveDataFilter().filter(record)
    assert record.getMessage() == "İstek gönderildi: Bearer ********"


# --- 4. Anahtar yönetimi (ATOP-49) ---


def test_key_rotation(db_session: Session) -> None:
    saved = (settings.encryption_key, settings.encryption_key_previous)
    old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    try:
        settings.encryption_key, settings.encryption_key_previous = old_key, ""
        crypto.reload_keys()
        row = ApiDefinition(
            name="Eski",
            method=HttpMethod.GET,
            url="https://x.com",
            headers=[],
            query_params=[],
            assertions=[],
            auth_type=AuthType.BEARER,
            auth_config_encrypted=crypto.encrypt_json({"token": "gizli"}),
        )
        db_session.add(row)
        db_session.commit()
        old_ciphertext = row.auth_config_encrypted

        # Yeni anahtara geçiş: eski anahtar sadece çözmek için tutulur
        settings.encryption_key, settings.encryption_key_previous = new_key, old_key
        crypto.reload_keys()
        assert crypto.decrypt_json(old_ciphertext) == {"token": "gizli"}
        assert rotate_all(db_session)["api_auth"] == 1

        # Eski anahtar kaldırıldı: yeniden şifrelenen kayıt okunur, eski şifreli metin okunmaz
        settings.encryption_key_previous = ""
        crypto.reload_keys()
        assert crypto.decrypt_json(db_session.get(ApiDefinition, row.id).auth_config_encrypted) == {
            "token": "gizli"
        }
        with pytest.raises(ValueError):
            crypto.decrypt_text(old_ciphertext)
    finally:
        settings.encryption_key, settings.encryption_key_previous = saved
        crypto.reload_keys()


def test_security_warnings() -> None:
    unsafe = settings.model_copy(
        update={
            "secret_key": "kisa",
            "encryption_key": "",
            "first_admin_password": "Admin12345",
            "cors_origins": "*",
        }
    )
    assert len(unsafe.security_warnings()) == 4

    safe = settings.model_copy(
        update={
            "secret_key": "x" * 40,
            "encryption_key": Fernet.generate_key().decode(),
            "first_admin_password": "Cok-Guclu-Bir-Sifre-2026",
            "cors_origins": "https://test.firma.com",
        }
    )
    assert safe.security_warnings() == []


def test_production_refuses_unsafe_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "kisa")
    with pytest.raises(RuntimeError, match="production"):
        check_security_settings()
