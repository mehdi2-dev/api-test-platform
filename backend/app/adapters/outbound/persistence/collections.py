"""Koleksiyon tabloları, domain eşlemesi ve repository'lerin SQLAlchemy adaptörleri.

Tablo şemaları eski modelle birebir aynıdır; migration gerekmez.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Session, relationship

from app.adapters.outbound.persistence.api_definitions import (  # noqa: F401  (eşlemeyi yükler)
    api_definitions_table,
)
from app.db.base import Base
from app.domain.api_definitions import ApiDefinition
from app.domain.collections import Collection, CollectionItem, CollectionRun, RunState, RunTrigger
from app.domain.testing.runs import RunStatus


def _timestamps() -> list[Column]:
    return [
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column(
            "updated_at",
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    ]


collections_table = Table(
    "collections",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(150), nullable=False, unique=True),
    Column("description", Text, nullable=True),
    Column("stop_on_failure", Boolean, nullable=False, default=False),
    Column("created_by_id", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    *_timestamps(),
)

collection_items_table = Table(
    "collection_items",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "collection_id",
        Integer,
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "api_definition_id",
        Integer,
        ForeignKey("api_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("position", Integer, nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("extractions", JSON, nullable=False, default=list),
)

collection_runs_table = Table(
    "collection_runs",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "collection_id",
        Integer,
        ForeignKey("collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column("collection_name", String(150), nullable=False),
    Column("environment_name", String(100), nullable=True),
    Column("triggered_by_id", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column(
        "status",
        Enum(RunStatus, name="run_status", values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        index=True,
    ),
    Column("state", String(20), nullable=False, default=RunState.COMPLETED.value),
    Column("trigger", String(20), nullable=False, default=RunTrigger.MANUAL.value),
    Column(
        "schedule_id",
        Integer,
        ForeignKey("schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column("error", Text, nullable=True),
    Column("total_steps", Integer, nullable=False, default=0),
    Column("passed_steps", Integer, nullable=False, default=0),
    Column("failed_steps", Integer, nullable=False, default=0),
    Column("skipped_steps", Integer, nullable=False, default=0),
    Column("elapsed_ms", Float, nullable=False, default=0),
    Column("steps", JSON, nullable=False, default=list),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    ),
)

# Adımın API tanımı bir ilişki: domain sınıfında alan olarak değil, burada tanımlanır
Base.registry.map_imperatively(
    CollectionItem,
    collection_items_table,
    properties={"api": relationship(ApiDefinition, lazy="selectin")},
)
Base.registry.map_imperatively(
    Collection,
    collections_table,
    properties={
        "items": relationship(
            CollectionItem,
            cascade="all, delete-orphan",
            order_by=collection_items_table.c.position,
            lazy="selectin",
        ),
    },
)
Base.registry.map_imperatively(CollectionRun, collection_runs_table)


class SqlAlchemyCollectionRepository:
    """CollectionRepository portunun SQLAlchemy adaptörü."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, collection_id: int) -> Collection | None:
        return self._session.get(Collection, collection_id)


class SqlAlchemyCollectionRunRepository:
    """CollectionRunRepository portunun SQLAlchemy adaptörü."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, run_id: int) -> CollectionRun | None:
        return self._session.get(CollectionRun, run_id)

    def save(self, run: CollectionRun) -> None:
        self._session.add(run)
        self._session.commit()
        self._session.refresh(run)

    def discard_changes(self) -> None:
        self._session.rollback()
