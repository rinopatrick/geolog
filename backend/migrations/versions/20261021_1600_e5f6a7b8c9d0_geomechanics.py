"""geomechanics models and runs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-21 16:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "geomechanics_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("model_type", sa.String(length=50), nullable=True),
        sa.Column("params_json", sa.Text(), nullable=True),
        sa.Column("calibration_json", sa.Text(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("geomechanics_models", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_geomechanics_models_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_geomechanics_models_well_id"), ["well_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_geomechanics_models_zone_id"), ["zone_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_geomechanics_models_status"), ["status"], unique=False)

    op.create_table(
        "geomechanics_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("log_run_id", sa.Integer(), nullable=False),
        sa.Column("depth_top", sa.Float(), nullable=True),
        sa.Column("depth_bottom", sa.Float(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["log_run_id"], ["log_runs.id"]),
        sa.ForeignKeyConstraint(["model_id"], ["geomechanics_models.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("geomechanics_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_geomechanics_runs_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_geomechanics_runs_model_id"), ["model_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_geomechanics_runs_log_run_id"), ["log_run_id"], unique=False)

def downgrade() -> None:
    for table, indexes in [
        ("geomechanics_runs", ["ix_geomechanics_runs_id", "ix_geomechanics_runs_model_id", "ix_geomechanics_runs_log_run_id"]),
        ("geomechanics_models", ["ix_geomechanics_models_id", "ix_geomechanics_models_well_id", "ix_geomechanics_models_zone_id", "ix_geomechanics_models_status"]),
    ]:
        with op.batch_alter_table(table, schema=None) as batch_op:
            for index in indexes:
                batch_op.drop_index(batch_op.f(index))
        op.drop_table(table)
