"""NMR T2 inversion tables

Revision ID: c3d4e5f6a7b8
Revises: 9f2c1a7b4d10
Create Date: 2026-10-21 13:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "9f2c1a7b4d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "nmr_inversions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("log_run_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=50), nullable=True),
        sa.Column("t2_bins_json", sa.Text(), nullable=True),
        sa.Column("cutoff_ms", sa.Float(), nullable=True),
        sa.Column("lambda_value", sa.Float(), nullable=True),
        sa.Column("n_depth", sa.Integer(), nullable=True),
        sa.Column("n_bins", sa.Integer(), nullable=True),
        sa.Column("params_hash", sa.String(length=64), nullable=True),
        sa.Column("engine_version", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.ForeignKeyConstraint(["log_run_id"], ["log_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("nmr_inversions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_nmr_inversions_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_nmr_inversions_well_id"), ["well_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_nmr_inversions_log_run_id"), ["log_run_id"], unique=False)

    op.create_table(
        "nmr_distributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inversion_id", sa.Integer(), nullable=False),
        sa.Column("n_depth", sa.Integer(), nullable=True),
        sa.Column("n_bins", sa.Integer(), nullable=True),
        sa.Column("depth_binary", sa.LargeBinary(), nullable=True),
        sa.Column("amplitudes", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(["inversion_id"], ["nmr_inversions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("nmr_distributions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_nmr_distributions_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_nmr_distributions_inversion_id"), ["inversion_id"], unique=True)

def downgrade() -> None:
    with op.batch_alter_table("nmr_distributions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nmr_distributions_inversion_id"))
        batch_op.drop_index(batch_op.f("ix_nmr_distributions_id"))
    op.drop_table("nmr_distributions")
    with op.batch_alter_table("nmr_inversions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nmr_inversions_log_run_id"))
        batch_op.drop_index(batch_op.f("ix_nmr_inversions_well_id"))
        batch_op.drop_index(batch_op.f("ix_nmr_inversions_id"))
    op.drop_table("nmr_inversions")
