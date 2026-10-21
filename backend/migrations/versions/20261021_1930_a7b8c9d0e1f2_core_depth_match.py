"""core depth matching

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-21 19:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table("core_plugs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("matched_log_md", sa.Float(), nullable=True))
    op.create_table(
        "core_depth_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("plug_id", sa.Integer(), nullable=False),
        sa.Column("log_run_id", sa.Integer(), nullable=False),
        sa.Column("core_md", sa.Float(), nullable=False),
        sa.Column("log_md", sa.Float(), nullable=False),
        sa.Column("shift", sa.Float(), nullable=True),
        sa.Column("residual", sa.Float(), nullable=True),
        sa.Column("method", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.ForeignKeyConstraint(["plug_id"], ["core_plugs.id"]),
        sa.ForeignKeyConstraint(["log_run_id"], ["log_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("core_depth_matches", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_core_depth_matches_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_core_depth_matches_well_id"), ["well_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_core_depth_matches_plug_id"), ["plug_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_core_depth_matches_log_run_id"), ["log_run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_core_depth_matches_status"), ["status"], unique=False)

def downgrade() -> None:
    for index in ["ix_core_depth_matches_id", "ix_core_depth_matches_well_id",
                  "ix_core_depth_matches_plug_id", "ix_core_depth_matches_log_run_id",
                  "ix_core_depth_matches_status"]:
        with op.batch_alter_table("core_depth_matches", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(index))
    op.drop_table("core_depth_matches")
    with op.batch_alter_table("core_plugs", schema=None) as batch_op:
        batch_op.drop_column("matched_log_md")
