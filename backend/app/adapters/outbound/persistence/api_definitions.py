"""API tanımı tablosu, domain eşlemesi ve ApiDefinitionRepository'nin SQLAlchemy adaptörü.

Tablo şeması eski modelle birebir aynıdır; migration gerekmez.
"""

from enum import StrEnum

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
    select,
)
from sqlalchemy.orm import Session

from app.adapters.outbound.persistence.base import Base
from app.domain.api_definitions import ApiDefinition, AuthType, BodyType, HttpMethod


def _values(enum_cls: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_cls]


api_definitions_table = Table(
    "api_definitions",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(150), nullable=False),
    Column("description", Text, nullable=True),
    Column(
        "method",
        Enum(HttpMethod, name="http_method", values_callable=_values),
        nullable=False,
        default=HttpMethod.GET,
    ),
    Column("url", String(2048), nullable=False),
    Column("headers", JSON, nullable=False, default=list),
    Column("query_params", JSON, nullable=False, default=list),
    Column(
        "body_type",
        Enum(BodyType, name="body_type", values_callable=_values),
        nullable=False,
        default=BodyType.NONE,
    ),
    Column("body", Text, nullable=True),
    Column(
        "auth_type",
        Enum(AuthType, name="auth_type", values_callable=_values),
        nullable=False,
        default=AuthType.NONE,
    ),
    Column("auth_config_encrypted", Text, nullable=True),
    Column("assertions", JSON, nullable=False, default=list),
    Column(
        "created_by_id",
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)

Base.registry.map_imperatively(ApiDefinition, api_definitions_table)


class SqlAlchemyApiDefinitionRepository:
    """ApiDefinitionRepository portunun SQLAlchemy adaptörü."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, api_id: int) -> ApiDefinition | None:
        return self._session.get(ApiDefinition, api_id)

    def search(self, name_contains: str | None = None) -> list[ApiDefinition]:
        table = api_definitions_table
        query = select(ApiDefinition).order_by(table.c.name, table.c.id)
        if name_contains:
            query = query.where(table.c.name.ilike(f"%{name_contains}%"))
        return list(self._session.scalars(query))

    def save(self, api: ApiDefinition) -> None:
        self._session.add(api)
        self._session.commit()
        self._session.refresh(api)

    def delete(self, api: ApiDefinition) -> None:
        self._session.delete(api)
        self._session.commit()
