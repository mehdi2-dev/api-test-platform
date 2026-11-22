"""api_definitions tablosu

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

http_method = sa.Enum(
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", name="http_method"
)
body_type = sa.Enum("none", "json", "text", name="body_type")
auth_type = sa.Enum("none", "bearer", "basic", "api_key", name="auth_type")


def upgrade() -> None:
    op.create_table(
        "api_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("method", http_method, nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("query_params", sa.JSON(), nullable=False),
        sa.Column("body_type", body_type, nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("auth_type", auth_type, nullable=False),
        sa.Column("auth_config_encrypted", sa.Text(), nullable=True),
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
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_api_definitions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_definitions")),
    )


def downgrade() -> None:
    op.drop_table("api_definitions")
    bind = op.get_bind()
    auth_type.drop(bind, checkfirst=True)
    body_type.drop(bind, checkfirst=True)
    http_method.drop(bind, checkfirst=True)
