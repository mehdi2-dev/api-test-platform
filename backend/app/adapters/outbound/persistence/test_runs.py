"""Test çalıştırma tablosu, domain eşlemesi ve ApiTestRunRepository'nin SQLAlchemy adaptörü.

Tablo şeması eski modelle birebir aynıdır; migration gerekmez.
"""

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
)
from sqlalchemy.orm import Session

from app.db.base import Base
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
