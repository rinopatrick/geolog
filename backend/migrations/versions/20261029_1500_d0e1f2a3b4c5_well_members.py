"""per-well ACL overrides

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-29 15:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "well_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("well_id", "subject", name="uq_well_member_subject"),
    )
    with op.batch_alter_table("well_members", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_well_members_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_well_members_well_id"), ["well_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_well_members_subject"), ["subject"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("well_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_well_members_subject"))
        batch_op.drop_index(batch_op.f("ix_well_members_well_id"))
        batch_op.drop_index(batch_op.f("ix_well_members_id"))
    op.drop_table("well_members")
