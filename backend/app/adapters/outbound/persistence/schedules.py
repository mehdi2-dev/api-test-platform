"""Zamanlama planı tablosu, domain eşlemesi ve ScheduleRepository'nin SQLAlchemy adaptörü.

Tablo şeması eski modelle birebir aynıdır; migration gerekmez.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    func,
    select,
)
from sqlalchemy.orm import Session, relationship

from app.adapters.outbound.persistence.base import Base
from app.adapters.outbound.persistence.collections import (  # noqa: F401  (eşlemeyi yükler)
    collections_table,
)
from app.adapters.outbound.persistence.environments import (  # noqa: F401
    environments_table,
)
from app.domain.collections import Collection, CollectionRun
from app.domain.environments import Environment
from app.domain.schedules import Schedule

schedules_table = Table(
    "schedules",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "collection_id",
        Integer,
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("cron", String(100), nullable=False),
    Column(
        "environment_id",
        Integer,
        ForeignKey("environments.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("confirm_production", Boolean, nullable=False, default=False),
    Column("next_run_at", DateTime(timezone=True), nullable=True, index=True),
    Column("last_run_at", DateTime(timezone=True), nullable=True),
    Column("last_run_id", Integer, nullable=True),
    Column("created_by_id", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)

Base.registry.map_imperatively(
    Schedule,
    schedules_table,
    properties={
        "collection": relationship(Collection, lazy="selectin"),
        "environment": relationship(Environment, lazy="selectin"),
    },
)


class SqlAlchemyScheduleRepository:
    """ScheduleRepository portunun SQLAlchemy adaptörü."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, schedule_id: int) -> Schedule | None:
        return self._session.get(Schedule, schedule_id)

    def list_all(self) -> list[Schedule]:
        table = schedules_table
        query = select(Schedule).order_by(table.c.enabled.desc(), table.c.next_run_at, table.c.id)
        return list(self._session.scalars(query))

    def save(self, schedule: Schedule) -> None:
        self._session.add(schedule)
        self._session.commit()
        self._session.refresh(schedule)

    def delete(self, schedule: Schedule) -> None:
        self._session.delete(schedule)
        self._session.commit()

    def due(self, now: datetime) -> list[Schedule]:
        table = schedules_table
        query = (
            select(Schedule)
            .where(table.c.enabled.is_(True), table.c.next_run_at <= now)
            .order_by(table.c.next_run_at)
            # Aynı anda iki zamanlayıcı çalışırsa aynı plan iki kez alınmasın (PostgreSQL)
            .with_for_update(skip_locked=True)
        )
        return list(self._session.scalars(query).all())

    def stage_run(self, run: CollectionRun) -> None:
        self._session.add(run)
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()
