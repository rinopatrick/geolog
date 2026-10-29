"""Add prospect portfolios.

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-11-01 12:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "a5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prospect_portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("inputs_json", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_prospect_portfolios_id", "prospect_portfolios", ["id"])
    op.create_index("ix_prospect_portfolios_project_id", "prospect_portfolios", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_prospect_portfolios_project_id", table_name="prospect_portfolios")
    op.drop_index("ix_prospect_portfolios_id", table_name="prospect_portfolios")
    op.drop_table("prospect_portfolios")
