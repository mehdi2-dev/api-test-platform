"""collections, collection_items, collection_runs ve test_runs.collection_run_id

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# run_status tipi 0005'te oluşturuldu; burada tekrar oluşturulmaz
run_status = postgresql.ENUM("passed", "failed", "error", name="run_status", create_type=False)


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stop_on_failure", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_collections_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collections")),
        sa.UniqueConstraint("name", name=op.f("uq_collections_name")),
    )
    op.create_table(
        "collection_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("api_definition_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("extractions", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
            name=op.f("fk_collection_items_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["api_definition_id"],
            ["api_definitions.id"],
            name=op.f("fk_collection_items_api_definition_id_api_definitions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_items")),
    )
    op.create_index(
        op.f("ix_collection_items_collection_id"), "collection_items", ["collection_id"]
    )
    op.create_index(
        op.f("ix_collection_items_api_definition_id"), "collection_items", ["api_definition_id"]
    )
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=True),
        sa.Column("collection_name", sa.String(length=150), nullable=False),
        sa.Column("environment_name", sa.String(length=100), nullable=True),
        sa.Column("triggered_by_id", sa.Integer(), nullable=True),
        sa.Column("status", run_status, nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("passed_steps", sa.Integer(), nullable=False),
        sa.Column("failed_steps", sa.Integer(), nullable=False),
        sa.Column("skipped_steps", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Float(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
            name=op.f("fk_collection_runs_collection_id_collections"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_id"],
            ["users.id"],
            name=op.f("fk_collection_runs_triggered_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_runs")),
    )
    op.create_index(op.f("ix_collection_runs_collection_id"), "collection_runs", ["collection_id"])
    op.create_index(op.f("ix_collection_runs_status"), "collection_runs", ["status"])
    op.create_index(op.f("ix_collection_runs_created_at"), "collection_runs", ["created_at"])

    op.add_column("test_runs", sa.Column("collection_run_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_test_runs_collection_run_id_collection_runs"),
        "test_runs",
        "collection_runs",
        ["collection_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_test_runs_collection_run_id"), "test_runs", ["collection_run_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_test_runs_collection_run_id"), table_name="test_runs")
    op.drop_constraint(
        op.f("fk_test_runs_collection_run_id_collection_runs"), "test_runs", type_="foreignkey"
    )
    op.drop_column("test_runs", "collection_run_id")
    op.drop_table("collection_runs")
    op.drop_table("collection_items")
    op.drop_table("collections")
