"""shared state for multi-instance rate limits, metrics and jobs

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-29 17:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shared_rate_buckets",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("reset_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "shared_rate_locks",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("until", sa.Float(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "shared_metric_workers",
        sa.Column("worker_id", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    op.create_table(
        "shared_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("created_epoch", sa.Float(), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=True),
        sa.Column("started_epoch", sa.Float(), nullable=True),
        sa.Column("finished_at", sa.String(length=40), nullable=True),
        sa.Column("finished_epoch", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("shared_jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_shared_jobs_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("shared_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_shared_jobs_status"))
    op.drop_table("shared_jobs")
    op.drop_table("shared_metric_workers")
    op.drop_table("shared_rate_locks")
    op.drop_table("shared_rate_buckets")
