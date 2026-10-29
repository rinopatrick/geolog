"""Add 3D fault geometry and polygon fields.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-10-31 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("seismic_fault_links") as batch:
        batch.add_column(sa.Column("geometry_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("polygon_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("seismic_fault_links") as batch:
        batch.drop_column("polygon_json")
        batch.drop_column("geometry_json")
