"""create comments table

Revision ID: 711c910e4077
Revises: 0642de8cc118
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "711c910e4077"
down_revision: str | Sequence[str] | None = "0642de8cc118"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_comments_task_id",
        "comments",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_comments_task_id",
        table_name="comments",
    )
    op.drop_table("comments")
