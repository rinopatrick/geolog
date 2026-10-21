"""data semantics: well unit target and depth control points

Revision ID: 9f2c1a7b4d10
Revises: 4b064cf3e9be
Create Date: 2026-10-21 12:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9f2c1a7b4d10"
down_revision: Union[str, None] = "4b064cf3e9be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table("wells", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("unit_system", sa.String(length=10), server_default="field", nullable=False)
        )

    op.create_table(
        "depth_control_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("log_run_id", sa.Integer(), nullable=False),
        sa.Column("md", sa.Float(), nullable=False),
        sa.Column("corrected_depth", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["log_run_id"], ["log_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("log_run_id", "md", name="uq_depth_control_points_run_md"),
    )
    with op.batch_alter_table("depth_control_points", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_depth_control_points_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_depth_control_points_log_run_id"), ["log_run_id"], unique=False
        )

def downgrade() -> None:
    with op.batch_alter_table("depth_control_points", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_depth_control_points_log_run_id"))
        batch_op.drop_index(batch_op.f("ix_depth_control_points_id"))
    op.drop_table("depth_control_points")
    with op.batch_alter_table("wells", schema=None) as batch_op:
        batch_op.drop_column("unit_system")
