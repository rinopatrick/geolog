"""Add base surface to prospects.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-11-01 18:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prospects") as batch:
        batch.add_column(sa.Column("base_surface_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_prospects_base_surface_id",
            "seismic_surfaces",
            ["base_surface_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("prospects") as batch:
        batch.drop_constraint("fk_prospects_base_surface_id", type_="foreignkey")
        batch.drop_column("base_surface_id")
