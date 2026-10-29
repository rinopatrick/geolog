"""Add section mode to seismic horizons.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-10-30 21:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("seismic_horizons") as batch:
        batch.add_column(sa.Column("mode", sa.String(length=20), nullable=True, server_default="line"))
        batch.add_column(sa.Column("section_value", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("seismic_horizons") as batch:
        batch.drop_column("section_value")
        batch.drop_column("mode")
