"""Giriş, token ve "ben kimim" testleri (ATOP-18)."""

from app.adapters.outbound.security.passwords import hash_password, verify_password
from app.adapters.outbound.security.tokens import create_refresh_token
from tests.conftest import TEST_PASSWORD


def test_password_is_hashed_not_stored_plain() -> None:
    hashed = hash_password("GizliSifre1")
    assert hashed != "GizliSifre1"
    assert verify_password("GizliSifre1", hashed)
    assert not verify_password("YanlisSifre", hashed)


def test_login_returns_tokens(api, make_user) -> None:
    make_user("tester@apitest.com")

    response = api.post(
        "/api/auth/login", json={"email": "tester@apitest.com", "password": TEST_PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0


def test_login_email_is_case_insensitive(api, make_user) -> None:
    make_user("tester@apitest.com")
    response = api.post(
        "/api/auth/login", json={"email": "Tester@ApiTest.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200


def test_login_wrong_password_returns_401(api, make_user) -> None:
    make_user("tester@apitest.com")
    response = api.post(
        "/api/auth/login", json={"email": "tester@apitest.com", "password": "YanlisSifre"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "E-posta veya şifre hatalı"


def test_login_unknown_email_gives_same_message(api, db_session) -> None:
    response = api.post(
        "/api/auth/login", json={"email": "yok@apitest.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "E-posta veya şifre hatalı"


def test_inactive_user_cannot_login(api, make_user) -> None:
    make_user("pasif@apitest.com", is_active=False)
    response = api.post(
        "/api/auth/login", json={"email": "pasif@apitest.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


def test_invalid_email_format_returns_422(api, db_session) -> None:
    response = api.post("/api/auth/login", json={"email": "eposta-degil", "password": "x"})
    assert response.status_code == 422


def test_me_returns_current_user(api, make_user, login) -> None:
    make_user("tester@apitest.com")
    response = api.get("/api/auth/me", headers=login("tester@apitest.com"))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "tester@apitest.com"
    assert body["role"] == "viewer"
    assert "hashed_password" not in body


def test_me_without_token_returns_401(api, db_session) -> None:
    assert api.get("/api/auth/me").status_code == 401


def test_me_with_garbage_token_returns_401(api, db_session) -> None:
    response = api.get("/api/auth/me", headers={"Authorization": "Bearer bozuk.token.degeri"})
    assert response.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(api, make_user) -> None:
    user = make_user("tester@apitest.com")
    refresh_token = create_refresh_token(user.id)
    response = api.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert response.status_code == 401


def test_refresh_returns_new_tokens(api, make_user) -> None:
    user = make_user("tester@apitest.com")
    response = api.post("/api/auth/refresh", json={"refresh_token": create_refresh_token(user.id)})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_access_token_cannot_be_used_to_refresh(api, make_user) -> None:
    make_user("tester@apitest.com")
    login_body = api.post(
        "/api/auth/login", json={"email": "tester@apitest.com", "password": TEST_PASSWORD}
    ).json()
    response = api.post("/api/auth/refresh", json={"refresh_token": login_body["access_token"]})
    assert response.status_code == 401
