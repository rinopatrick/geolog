"""Add 3D seismic migrations.

Revision ID: d9e0f1a2b3c4
Revises: c7d8e9f0a1b2
Create Date: 2026-11-02 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "d9e0f1a2b3c4"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seismic_migrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("seismic_lines.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("velocity_m_s", sa.Float(), nullable=False),
        sa.Column("inline_spacing_m", sa.Float(), nullable=False),
        sa.Column("crossline_spacing_m", sa.Float(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("inlines_json", sa.Text(), nullable=True),
        sa.Column("crosslines_json", sa.Text(), nullable=True),
        sa.Column("depths_json", sa.Text(), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_seismic_migrations_id", "seismic_migrations", ["id"])
    op.create_index("ix_seismic_migrations_line_id", "seismic_migrations", ["line_id"])


def downgrade() -> None:
    op.drop_index("ix_seismic_migrations_line_id", table_name="seismic_migrations")
    op.drop_index("ix_seismic_migrations_id", table_name="seismic_migrations")
    op.drop_table("seismic_migrations")
