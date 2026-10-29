"""Add gridded seismic surfaces.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-10-31 12:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seismic_surfaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("seismic_lines.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("grid_json", sa.Text(), nullable=True),
        sa.Column("inlines_json", sa.Text(), nullable=True),
        sa.Column("crosslines_json", sa.Text(), nullable=True),
        sa.Column("sample_interval_ms", sa.Float(), nullable=True),
        sa.Column("inline_spacing_m", sa.Float(), nullable=True),
        sa.Column("crossline_spacing_m", sa.Float(), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_seismic_surfaces_id", "seismic_surfaces", ["id"])
    op.create_index("ix_seismic_surfaces_line_id", "seismic_surfaces", ["line_id"])


def downgrade() -> None:
    op.drop_index("ix_seismic_surfaces_line_id", table_name="seismic_surfaces")
    op.drop_index("ix_seismic_surfaces_id", table_name="seismic_surfaces")
    op.drop_table("seismic_surfaces")
