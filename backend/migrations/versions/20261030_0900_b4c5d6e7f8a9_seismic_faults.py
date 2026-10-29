"""seismic fault picks

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-30 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seismic_faults",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("picks_json", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["line_id"], ["seismic_lines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("seismic_faults", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_seismic_faults_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_seismic_faults_line_id"), ["line_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("seismic_faults", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_seismic_faults_line_id"))
        batch_op.drop_index(batch_op.f("ix_seismic_faults_id"))
    op.drop_table("seismic_faults")
