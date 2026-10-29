"""Add fault surfaces and compartments.

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-11-01 15:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fault_surfaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("seismic_lines.id"), nullable=False),
        sa.Column("link_id", sa.Integer(), sa.ForeignKey("seismic_fault_links.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("grid_json", sa.Text(), nullable=True),
        sa.Column("inlines_json", sa.Text(), nullable=True),
        sa.Column("crosslines_json", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=20), nullable=True),
        sa.Column("velocity_model_id", sa.Integer(), sa.ForeignKey("velocity_models.id"), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_fault_surfaces_id", "fault_surfaces", ["id"])
    op.create_index("ix_fault_surfaces_line_id", "fault_surfaces", ["line_id"])
    op.create_index("ix_fault_surfaces_link_id", "fault_surfaces", ["link_id"])
    with op.batch_alter_table("seismic_surfaces") as batch:
        batch.add_column(sa.Column("compartments_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("seismic_surfaces") as batch:
        batch.drop_column("compartments_json")
    op.drop_index("ix_fault_surfaces_link_id", table_name="fault_surfaces")
    op.drop_index("ix_fault_surfaces_line_id", table_name="fault_surfaces")
    op.drop_index("ix_fault_surfaces_id", table_name="fault_surfaces")
    op.drop_table("fault_surfaces")
