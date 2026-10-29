"""source rock analysis metadata

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-10-30 12:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_rock_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("log_run_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("porosity_mode", sa.String(length=20), nullable=True),
        sa.Column("lom", sa.Float(), nullable=True),
        sa.Column("toc_base", sa.Float(), nullable=True),
        sa.Column("rt_base", sa.Float(), nullable=True),
        sa.Column("porosity_base", sa.Float(), nullable=True),
        sa.Column("toc_curve", sa.String(length=30), nullable=True),
        sa.Column("vker_curve", sa.String(length=30), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.ForeignKeyConstraint(["log_run_id"], ["log_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("source_rock_analyses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_source_rock_analyses_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_source_rock_analyses_well_id"), ["well_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_source_rock_analyses_log_run_id"), ["log_run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("source_rock_analyses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_source_rock_analyses_log_run_id"))
        batch_op.drop_index(batch_op.f("ix_source_rock_analyses_well_id"))
        batch_op.drop_index(batch_op.f("ix_source_rock_analyses_id"))
    op.drop_table("source_rock_analyses")
