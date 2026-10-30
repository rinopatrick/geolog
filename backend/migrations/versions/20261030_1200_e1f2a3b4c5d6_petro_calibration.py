"""Add GR endpoints and shale porosity to petro params.

Revision ID: f0a1b2c3d4e5
Revises: d9e0f1a2b3c4
Create Date: 2026-10-30 12:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "f0a1b2c3d4e5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("petro_params") as batch:
        batch.add_column(sa.Column("gr_clean", sa.Float(), nullable=True))
        batch.add_column(sa.Column("gr_shale", sa.Float(), nullable=True))
        batch.add_column(sa.Column("phi_sh", sa.Float(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("petro_params") as batch:
        batch.drop_column("phi_sh")
        batch.drop_column("gr_shale")
        batch.drop_column("gr_clean")
