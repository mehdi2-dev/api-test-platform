"""Ortam tabloları, domain eşlemesi ve EnvironmentRepository'nin SQLAlchemy adaptörü.

Tablo şemaları eski modelle birebir aynıdır; migration gerekmez.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Session, relationship

from app.adapters.outbound.persistence.base import Base
from app.domain.environments import Environment, EnvironmentVariable

environments_table = Table(
    "environments",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("description", Text, nullable=True),
    Column("is_production", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)

environment_variables_table = Table(
    "environment_variables",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "environment_id",
        Integer,
        ForeignKey("environments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("key", String(100), nullable=False),
    # is_secret ise şifreli metin, değilse düz değer
    Column("value", Text, nullable=False, default=""),
    Column("is_secret", Boolean, nullable=False, default=False),
    UniqueConstraint("environment_id", "key"),
)

Base.registry.map_imperatively(EnvironmentVariable, environment_variables_table)
Base.registry.map_imperatively(
    Environment,
    environments_table,
    properties={
        "variables": relationship(
            EnvironmentVariable,
            cascade="all, delete-orphan",
            order_by=environment_variables_table.c.id,
            lazy="selectin",
        ),
    },
)


class SqlAlchemyEnvironmentRepository:
    """EnvironmentRepository portunun SQLAlchemy adaptörü."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, environment_id: int) -> Environment | None:
        return self._session.get(Environment, environment_id)

    def get_by_name(self, name: str) -> Environment | None:
        return self._session.scalar(select(Environment).where(environments_table.c.name == name))

    def list_all(self) -> list[Environment]:
        query = select(Environment).order_by(
            environments_table.c.is_production, environments_table.c.name
        )
        return list(self._session.scalars(query))

    def save(self, environment: Environment) -> None:
        self._session.add(environment)
        self._session.commit()
        self._session.refresh(environment)

    def delete(self, environment: Environment) -> None:
        self._session.delete(environment)
        self._session.commit()
