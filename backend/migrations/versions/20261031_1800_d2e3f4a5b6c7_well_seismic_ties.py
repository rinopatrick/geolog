"""Add well-to-seismic ties.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-31 18:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "well_seismic_ties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("well_id", sa.Integer(), sa.ForeignKey("wells.id"), nullable=False),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("seismic_lines.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("inline", sa.Integer(), nullable=False),
        sa.Column("crossline", sa.Integer(), nullable=False),
        sa.Column("checkshot_json", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("shift_ms", sa.Float(), nullable=True),
        sa.Column("correlation", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_well_seismic_ties_id", "well_seismic_ties", ["id"])
    op.create_index("ix_well_seismic_ties_well_id", "well_seismic_ties", ["well_id"])
    op.create_index("ix_well_seismic_ties_line_id", "well_seismic_ties", ["line_id"])


def downgrade() -> None:
    op.drop_index("ix_well_seismic_ties_line_id", table_name="well_seismic_ties")
    op.drop_index("ix_well_seismic_ties_well_id", table_name="well_seismic_ties")
    op.drop_index("ix_well_seismic_ties_id", table_name="well_seismic_ties")
    op.drop_table("well_seismic_ties")
