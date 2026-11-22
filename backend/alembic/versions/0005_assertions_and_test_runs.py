"""api_definitions.assertions sütunu ve test_runs tablosu

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

run_status = sa.Enum("passed", "failed", "error", name="run_status")


def upgrade() -> None:
    op.add_column(
        "api_definitions",
        sa.Column("assertions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_table(
        "test_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("api_definition_id", sa.Integer(), nullable=True),
        sa.Column("api_name", sa.String(length=150), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("environment_name", sa.String(length=100), nullable=True),
        sa.Column("triggered_by_id", sa.Integer(), nullable=True),
        sa.Column("status", run_status, nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("elapsed_ms", sa.Float(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("assertion_results", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["api_definition_id"],
            ["api_definitions.id"],
            name=op.f("fk_test_runs_api_definition_id_api_definitions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_id"],
            ["users.id"],
            name=op.f("fk_test_runs_triggered_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_runs")),
    )
    op.create_index(op.f("ix_test_runs_api_definition_id"), "test_runs", ["api_definition_id"])
    op.create_index(op.f("ix_test_runs_status"), "test_runs", ["status"])
    op.create_index(op.f("ix_test_runs_created_at"), "test_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_test_runs_created_at"), table_name="test_runs")
    op.drop_index(op.f("ix_test_runs_status"), table_name="test_runs")
    op.drop_index(op.f("ix_test_runs_api_definition_id"), table_name="test_runs")
    op.drop_table("test_runs")
    run_status.drop(op.get_bind(), checkfirst=True)
    op.drop_column("api_definitions", "assertions")
