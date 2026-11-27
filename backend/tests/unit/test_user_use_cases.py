"""Giriş ve kullanıcı yönetimi use case'leri, bellek içi adaptörlerle.

Hexagonal mimarinin faydası: aynı use case'ler gerçekte SQLAlchemy/bcrypt/JWT ile,
burada ise sahte portlarla çalışır; use case kodunda tek satır değişmez.
"""

import pytest

from app.application.errors import AuthenticationFailed, TooManyAttempts
from app.application.use_cases.auth import AuthenticateUser, Login, RefreshTokens
from app.application.use_cases.users import CreateUser, EnsureFirstAdmin, GetUser, UpdateUser
from app.domain.errors import Conflict, NotFound
from app.domain.users import Role, User
from tests.fakes import (
    FakeLoginLimiter,
    FakeTokenService,
    InMemoryUserRepository,
    PlainPasswordHasher,
)


@pytest.fixture
def users() -> InMemoryUserRepository:
    repo = InMemoryUserRepository()
    for email, role, active in [
        ("admin@apitest.com", Role.ADMIN, True),
        ("tester@apitest.com", Role.TESTER, True),
        ("pasif@apitest.com", Role.VIEWER, False),
    ]:
        repo.save(
            User(
                email=email,
                full_name=email,
                hashed_password="hashed:Sifre12345",
                role=role,
                is_active=active,
            )
        )
    return repo


@pytest.fixture
def limiter() -> FakeLoginLimiter:
    return FakeLoginLimiter(max_attempts=3)


@pytest.fixture
def login(users, limiter) -> Login:
    return Login(users, PlainPasswordHasher(), FakeTokenService(), limiter)


def test_login_returns_tokens_and_ignores_email_case(login) -> None:
    pair = login("Tester@ApiTest.com", "Sifre12345", client="1.2.3.4")
    assert pair.access_token == "access:2"


def test_wrong_password_and_unknown_email_give_same_error(login) -> None:
    with pytest.raises(AuthenticationFailed) as wrong:
        login("tester@apitest.com", "Yanlis", client="ip")
    with pytest.raises(AuthenticationFailed) as unknown:
        login("yok@apitest.com", "Sifre12345", client="ip")
    assert wrong.value.message == unknown.value.message == "E-posta veya şifre hatalı"


def test_inactive_user_cannot_login(login) -> None:
    with pytest.raises(AuthenticationFailed, match="pasif"):
        login("pasif@apitest.com", "Sifre12345", client="ip")


def test_too_many_failures_lock_the_login(login) -> None:
    for _ in range(3):
        with pytest.raises(AuthenticationFailed):
            login("tester@apitest.com", "Yanlis", client="ip")

    with pytest.raises(TooManyAttempts) as locked:
        login("tester@apitest.com", "Sifre12345", client="ip")
    assert locked.value.retry_after == 600
    assert "10 dakika" in locked.value.message


def test_lock_is_per_client(login) -> None:
    for _ in range(3):
        with pytest.raises(AuthenticationFailed):
            login("tester@apitest.com", "Yanlis", client="saldirgan")

    assert login("tester@apitest.com", "Sifre12345", client="ofis").access_token


def test_successful_login_resets_failures(login, limiter) -> None:
    with pytest.raises(AuthenticationFailed):
        login("tester@apitest.com", "Yanlis", client="ip")
    login("tester@apitest.com", "Sifre12345", client="ip")
    assert limiter.failures == {}


def test_refresh_needs_refresh_token(users) -> None:
    refresh = RefreshTokens(users, FakeTokenService())

    assert refresh("refresh:2").access_token == "access:2"
    with pytest.raises(AuthenticationFailed, match="Refresh token"):
        refresh("access:2")


def test_authenticate_rejects_inactive_and_unknown_users(users) -> None:
    authenticate = AuthenticateUser(users, FakeTokenService())

    assert authenticate("access:1").email == "admin@apitest.com"
    for token in ["access:3", "access:99", "refresh:1", "bozuk"]:
        with pytest.raises(AuthenticationFailed):
            authenticate(token)


def test_create_user_hashes_password_and_rejects_duplicate(users) -> None:
    create = CreateUser(users, PlainPasswordHasher())

    user = create(email="Yeni@ApiTest.com", full_name="Yeni", password="Gizli123", role=Role.TESTER)

    assert user.id is not None
    assert user.email == "yeni@apitest.com"
    assert user.hashed_password == "hashed:Gizli123"
    with pytest.raises(Conflict):
        create(email="yeni@apitest.com", full_name="Tekrar", password="x", role=Role.VIEWER)


def test_update_user_hashes_new_password(users) -> None:
    admin = users.get(1)

    user = UpdateUser(users, PlainPasswordHasher())(admin, 2, password="YeniSifre1")

    assert user.hashed_password == "hashed:YeniSifre1"


def test_unknown_user_is_not_found(users) -> None:
    with pytest.raises(NotFound):
        GetUser(users)(99)


def test_first_admin_only_when_there_are_no_users() -> None:
    users = InMemoryUserRepository()
    ensure = EnsureFirstAdmin(users, PlainPasswordHasher())

    admin = ensure(email="Admin@ApiTest.com", full_name="Yönetici", password="Admin12345")

    assert admin is not None and admin.role == Role.ADMIN and admin.email == "admin@apitest.com"
    assert ensure(email="baska@apitest.com", full_name="X", password="y") is None
    assert users.count() == 1
