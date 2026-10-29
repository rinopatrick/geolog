"""Add 3D SEG-Y trace headers and linked fault candidates.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-10-30 18:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("seismic_lines") as batch:
        batch.add_column(sa.Column("trace_headers_path", sa.String(length=500), nullable=True))
    op.create_table(
        "seismic_fault_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("seismic_lines.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=True, server_default="#f85149"),
        sa.Column("points_json", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("inline_start", sa.Integer(), nullable=True),
        sa.Column("inline_end", sa.Integer(), nullable=True),
        sa.Column("crossline_center", sa.Float(), nullable=True),
        sa.Column("sample_center", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_seismic_fault_links_line_id", "seismic_fault_links", ["line_id"])
    op.create_index("ix_seismic_fault_links_id", "seismic_fault_links", ["id"])


def downgrade() -> None:
    op.drop_index("ix_seismic_fault_links_id", table_name="seismic_fault_links")
    op.drop_index("ix_seismic_fault_links_line_id", table_name="seismic_fault_links")
    op.drop_table("seismic_fault_links")
    with op.batch_alter_table("seismic_lines") as batch:
        batch.drop_column("trace_headers_path")
