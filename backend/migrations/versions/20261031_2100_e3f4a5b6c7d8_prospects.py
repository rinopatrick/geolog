"""Add prospect volumetrics.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-31 21:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prospects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("seismic_lines.id"), nullable=True),
        sa.Column("surface_id", sa.Integer(), sa.ForeignKey("seismic_surfaces.id"), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("contact_depth_m", sa.Float(), nullable=True),
        sa.Column("grv_m3", sa.Float(), nullable=True),
        sa.Column("area_m2", sa.Float(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_prospects_id", "prospects", ["id"])
    op.create_index("ix_prospects_project_id", "prospects", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_prospects_project_id", table_name="prospects")
    op.drop_index("ix_prospects_id", table_name="prospects")
    op.drop_table("prospects")
