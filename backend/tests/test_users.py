"""Rol bazlı yetki ve kullanıcı yönetimi testleri (ATOP-19, ATOP-20)."""

import pytest

from app.db.init_db import ensure_first_admin
from app.models.user import Role, User

NEW_USER = {
    "email": "yeni@apitest.com",
    "full_name": "Yeni Kullanıcı",
    "password": "YeniSifre123",
    "role": "tester",
}


@pytest.fixture
def admin_headers(make_user, login) -> dict[str, str]:
    make_user("admin@apitest.com", role=Role.ADMIN)
    return login("admin@apitest.com")


def test_admin_can_list_users(api, admin_headers) -> None:
    response = api.get("/api/users", headers=admin_headers)
    assert response.status_code == 200
    assert [u["email"] for u in response.json()] == ["admin@apitest.com"]


@pytest.mark.parametrize("role", [Role.TESTER, Role.VIEWER])
def test_non_admin_cannot_manage_users(api, make_user, login, role) -> None:
    make_user("rol@apitest.com", role=role)
    headers = login("rol@apitest.com")

    assert api.get("/api/users", headers=headers).status_code == 403
    assert api.post("/api/users", json=NEW_USER, headers=headers).status_code == 403


def test_users_endpoint_requires_login(api, db_session) -> None:
    assert api.get("/api/users").status_code == 401


def test_admin_creates_user_who_can_then_login(api, admin_headers) -> None:
    response = api.post("/api/users", json=NEW_USER, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["role"] == "tester"
    login = api.post(
        "/api/auth/login", json={"email": NEW_USER["email"], "password": NEW_USER["password"]}
    )
    assert login.status_code == 200


def test_duplicate_email_returns_409(api, admin_headers) -> None:
    api.post("/api/users", json=NEW_USER, headers=admin_headers)
    response = api.post("/api/users", json=NEW_USER, headers=admin_headers)
    assert response.status_code == 409


def test_short_password_returns_422(api, admin_headers) -> None:
    response = api.post("/api/users", json={**NEW_USER, "password": "kisa"}, headers=admin_headers)
    assert response.status_code == 422


def test_password_over_72_bytes_returns_422(api, admin_headers) -> None:
    turkce_uzun = "ş" * 40  # 40 karakter ama 80 bayt
    response = api.post(
        "/api/users", json={**NEW_USER, "password": turkce_uzun}, headers=admin_headers
    )
    assert response.status_code == 422


def test_admin_changes_role_and_deactivates_user(api, admin_headers, make_user, login) -> None:
    user = make_user("tester@apitest.com", role=Role.TESTER)

    response = api.patch(
        f"/api/users/{user.id}", json={"role": "viewer", "is_active": False}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    assert response.json()["is_active"] is False
    pasif_login = api.post(
        "/api/auth/login", json={"email": "tester@apitest.com", "password": "Sifre12345"}
    )
    assert pasif_login.status_code == 401


def test_admin_cannot_demote_or_deactivate_self(api, admin_headers) -> None:
    me = api.get("/api/auth/me", headers=admin_headers).json()

    demote = api.patch(f"/api/users/{me['id']}", json={"role": "viewer"}, headers=admin_headers)
    deactivate = api.patch(
        f"/api/users/{me['id']}", json={"is_active": False}, headers=admin_headers
    )

    assert demote.status_code == 400
    assert deactivate.status_code == 400


def test_unknown_user_returns_404(api, admin_headers) -> None:
    assert api.get("/api/users/9999", headers=admin_headers).status_code == 404


def test_first_admin_created_only_when_no_users(db_session) -> None:
    created = ensure_first_admin(db_session)
    assert created is not None and created.role == Role.ADMIN

    assert ensure_first_admin(db_session) is None
    assert db_session.query(User).count() == 1
