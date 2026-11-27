"""Test çalıştırma tablosu, domain eşlemesi ve ApiTestRunRepository'nin SQLAlchemy adaptörü.

Tablo şeması eski modelle birebir aynıdır; migration gerekmez.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
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
    select,
)
from sqlalchemy.orm import Session

from app.adapters.outbound.persistence.base import Base
from app.domain.reporting import RunHistoryFilter
from app.domain.testing.runs import ApiTestRun, RunStatus

test_runs_table = Table(
    "test_runs",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "api_definition_id",
        Integer,
        ForeignKey("api_definitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    Column("api_name", String(150), nullable=False),
    Column("method", String(10), nullable=False),
    Column("environment_name", String(100), nullable=True),
    Column(
        "triggered_by_id",
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column(
        "collection_run_id",
        Integer,
        ForeignKey("collection_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    ),
    Column(
        "status",
        Enum(RunStatus, name="run_status", values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        index=True,
    ),
    Column("status_code", Integer, nullable=True),
    Column("elapsed_ms", Float, nullable=False, default=0),
    Column("passed_count", Integer, nullable=False, default=0),
    Column("failed_count", Integer, nullable=False, default=0),
    Column("error", Text, nullable=True),
    Column("request", JSON, nullable=False, default=dict),
    Column("response", JSON, nullable=True),
    Column("assertion_results", JSON, nullable=False, default=list),
    Column(
        "created_at",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    ),
)

Base.registry.map_imperatively(ApiTestRun, test_runs_table)


class SqlAlchemyApiTestRunRepository:
    """ApiTestRunRepository portunun SQLAlchemy adaptörü."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: ApiTestRun) -> None:
        self._session.add(run)
        self._session.commit()
        self._session.refresh(run)

    def for_collection_run(self, collection_run_id: int) -> list[ApiTestRun]:
        query = select(ApiTestRun).where(test_runs_table.c.collection_run_id == collection_run_id)
        return list(self._session.scalars(query))

    def get(self, run_id: int) -> ApiTestRun | None:
        return self._session.get(ApiTestRun, run_id)

    @staticmethod
    def _newest_first(query):
        return query.order_by(test_runs_table.c.created_at.desc(), test_runs_table.c.id.desc())

    def recent(
        self, *, api_id: int | None = None, status: RunStatus | None = None, limit: int = 20
    ) -> list[ApiTestRun]:
        query = self._newest_first(select(ApiTestRun))
        if api_id is not None:
            query = query.where(test_runs_table.c.api_definition_id == api_id)
        if status is not None:
            query = query.where(test_runs_table.c.status == status)
        return list(self._session.scalars(query.limit(limit)))

    def search(
        self, filters: RunHistoryFilter, *, offset: int, limit: int
    ) -> tuple[int, list[ApiTestRun]]:
        table = test_runs_table
        conditions = []
        if filters.name_contains:
            conditions.append(table.c.api_name.ilike(f"%{filters.name_contains}%"))
        if filters.api_id is not None:
            conditions.append(table.c.api_definition_id == filters.api_id)
        if filters.status is not None:
            conditions.append(table.c.status == filters.status)
        if filters.environment == "none":
            conditions.append(table.c.environment_name.is_(None))
        elif filters.environment:
            conditions.append(table.c.environment_name == filters.environment)
        if filters.source == "single":
            conditions.append(table.c.collection_run_id.is_(None))
        elif filters.source == "collection":
            conditions.append(table.c.collection_run_id.is_not(None))
        if filters.created_from:
            conditions.append(table.c.created_at >= filters.created_from)
        if filters.created_before:
            conditions.append(table.c.created_at < filters.created_before)

        total = self._session.scalar(select(func.count()).select_from(table).where(*conditions))
        query = self._newest_first(select(ApiTestRun).where(*conditions))
        items = list(self._session.scalars(query.offset(offset).limit(limit)))
        return total or 0, items

    def since(self, moment: datetime) -> list[ApiTestRun]:
        query = select(ApiTestRun).where(test_runs_table.c.created_at >= moment)
        return list(self._session.scalars(query))

    def last_passed_before(self, api_definition_id: int, run_id: int) -> ApiTestRun | None:
        table = test_runs_table
        return self._session.scalar(
            select(ApiTestRun)
            .where(
                table.c.api_definition_id == api_definition_id,
                table.c.status == RunStatus.PASSED,
                table.c.id < run_id,
            )
            .order_by(table.c.id.desc())
            .limit(1)
        )
