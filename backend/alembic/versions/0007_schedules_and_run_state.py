"""schedules tablosu; collection_runs'a durum (state), tetikleyici ve hata alanları

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("cron", sa.String(length=100), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("confirm_production", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
            name=op.f("fk_schedules_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name=op.f("fk_schedules_environment_id_environments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_schedules_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedules")),
    )
    op.create_index(op.f("ix_schedules_collection_id"), "schedules", ["collection_id"])
    op.create_index(op.f("ix_schedules_next_run_at"), "schedules", ["next_run_at"])

    op.alter_column("collection_runs", "status", existing_nullable=False, nullable=True)
    op.add_column(
        "collection_runs",
        sa.Column("state", sa.String(length=20), nullable=False, server_default="completed"),
    )
    op.add_column(
        "collection_runs",
        sa.Column("trigger", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.add_column("collection_runs", sa.Column("schedule_id", sa.Integer(), nullable=True))
    op.add_column("collection_runs", sa.Column("error", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_collection_runs_schedule_id_schedules"),
        "collection_runs",
        "schedules",
        ["schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_collection_runs_schedule_id"), "collection_runs", ["schedule_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_collection_runs_schedule_id"), table_name="collection_runs")
    op.drop_constraint(
        op.f("fk_collection_runs_schedule_id_schedules"), "collection_runs", type_="foreignkey"
    )
    op.drop_column("collection_runs", "error")
    op.drop_column("collection_runs", "schedule_id")
    op.drop_column("collection_runs", "trigger")
    op.drop_column("collection_runs", "state")
    op.execute("UPDATE collection_runs SET status = 'error' WHERE status IS NULL")
    op.alter_column("collection_runs", "status", existing_nullable=True, nullable=False)
    op.drop_index(op.f("ix_schedules_next_run_at"), table_name="schedules")
    op.drop_index(op.f("ix_schedules_collection_id"), table_name="schedules")
    op.drop_table("schedules")
