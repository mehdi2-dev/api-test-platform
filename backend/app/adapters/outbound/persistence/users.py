"""Kullanıcı tablosu, domain User eşlemesi ve UserRepository'nin SQLAlchemy adaptörü.

Domain sınıfına ORM etiketi koymadan tabloyla eşliyoruz (imperative mapping).
Tablo şeması eski modelle birebir aynıdır; migration gerekmez.
"""

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Table, func, select
from sqlalchemy.orm import Session

from app.adapters.outbound.persistence.base import Base
from app.domain.users import Role, User

users_table = Table(
    "users",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(255), nullable=False, unique=True, index=True),
    Column("full_name", String(100), nullable=False),
    Column("hashed_password", String(255), nullable=False),
    Column(
        "role",
        Enum(Role, name="user_role", values_callable=lambda roles: [r.value for r in roles]),
        nullable=False,
        default=Role.VIEWER,
    ),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)

Base.registry.map_imperatively(User, users_table)


class SqlAlchemyUserRepository:
    """UserRepository portunun SQLAlchemy adaptörü."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(users_table.c.email == email))

    def list_all(self) -> list[User]:
        return list(self._session.scalars(select(User).order_by(users_table.c.id)))

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(users_table)) or 0

    def save(self, user: User) -> None:
        self._session.add(user)
        self._session.commit()
        self._session.refresh(user)
