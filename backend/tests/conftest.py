"""Testler için ortak hazırlık.

Testler gerçek PostgreSQL yerine bellekte çalışan bir SQLite veritabanı kullanır:
her test temiz bir veritabanıyla başlar ve Docker gerektirmez.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.outbound.persistence.session import get_db
from app.adapters.outbound.persistence.tables import Base
from app.adapters.outbound.security.login_limiter import login_limiter
from app.adapters.outbound.security.passwords import hash_password
from app.domain.users import Role, User
from app.main import app

TEST_PASSWORD = "Sifre12345"


@pytest.fixture(autouse=True)
def _reset_login_limiter() -> Iterator[None]:
    """Her test giriş denemesi sayacı sıfırken başlasın."""
    login_limiter.reset()
    yield
    login_limiter.reset()


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = testing_session()

    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        engine.dispose()


@pytest.fixture
def api(db_session: Session) -> TestClient:
    """Test veritabanına bağlı istemci."""
    return TestClient(app)


@pytest.fixture
def make_user(db_session: Session) -> Callable[..., User]:
    def _make(
        email: str = "kullanici@apitest.com",
        role: Role = Role.VIEWER,
        is_active: bool = True,
        password: str = TEST_PASSWORD,
    ) -> User:
        user = User(
            email=email,
            full_name=email.split("@")[0],
            hashed_password=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        db_session.commit()
        return user

    return _make


@pytest.fixture
def login(api: TestClient) -> Callable[[str, str], dict[str, str]]:
    """Giriş yapıp Authorization başlığını döndürür."""

    def _login(email: str, password: str = TEST_PASSWORD) -> dict[str, str]:
        response = api.post("/api/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
