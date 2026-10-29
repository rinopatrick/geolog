"""Add fluid type to prospects.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-11-01 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prospects") as batch:
        batch.add_column(sa.Column("fluid_type", sa.String(length=20), nullable=True, server_default="oil"))


def downgrade() -> None:
    with op.batch_alter_table("prospects") as batch:
        batch.drop_column("fluid_type")
