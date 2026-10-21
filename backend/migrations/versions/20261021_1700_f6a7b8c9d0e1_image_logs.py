"""image assets and dip picks

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-21 17:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "image_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("log_run_id", sa.Integer(), nullable=True),
        sa.Column("image_type", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("depth_top", sa.Float(), nullable=False),
        sa.Column("depth_bottom", sa.Float(), nullable=False),
        sa.Column("azimuth_start", sa.Float(), nullable=True),
        sa.Column("azimuth_end", sa.Float(), nullable=True),
        sa.Column("borehole_radius", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["log_run_id"], ["log_runs.id"]),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("image_assets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_image_assets_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_image_assets_well_id"), ["well_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_image_assets_log_run_id"), ["log_run_id"], unique=False)

    op.create_table(
        "dip_picks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Float(), nullable=False),
        sa.Column("dip_angle", sa.Float(), nullable=False),
        sa.Column("dip_azimuth", sa.Float(), nullable=False),
        sa.Column("amplitude", sa.Float(), nullable=True),
        sa.Column("r2", sa.Float(), nullable=True),
        sa.Column("quality", sa.String(length=20), nullable=True),
        sa.Column("method", sa.String(length=30), nullable=True),
        sa.Column("picked_by", sa.String(length=120), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("trace_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["image_assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("dip_picks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_dip_picks_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_dip_picks_asset_id"), ["asset_id"], unique=False)

def downgrade() -> None:
    for table, indexes in [
        ("dip_picks", ["ix_dip_picks_id", "ix_dip_picks_asset_id"]),
        ("image_assets", ["ix_image_assets_id", "ix_image_assets_well_id", "ix_image_assets_log_run_id"]),
    ]:
        with op.batch_alter_table(table, schema=None) as batch_op:
            for index in indexes:
                batch_op.drop_index(batch_op.f(index))
        op.drop_table(table)
