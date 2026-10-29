"""SEG-Y lines and horizons

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-29 20:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seismic_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("format_code", sa.Integer(), nullable=True),
        sa.Column("sample_interval_ms", sa.Float(), nullable=True),
        sa.Column("samples_per_trace", sa.Integer(), nullable=True),
        sa.Column("trace_count", sa.Integer(), nullable=True),
        sa.Column("inline_min", sa.Integer(), nullable=True),
        sa.Column("inline_max", sa.Integer(), nullable=True),
        sa.Column("crossline_min", sa.Integer(), nullable=True),
        sa.Column("crossline_max", sa.Integer(), nullable=True),
        sa.Column("amplitude_min", sa.Float(), nullable=True),
        sa.Column("amplitude_max", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("seismic_lines", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_seismic_lines_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_seismic_lines_project_id"), ["project_id"], unique=False)

    op.create_table(
        "seismic_horizons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("picks_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["line_id"], ["seismic_lines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("seismic_horizons", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_seismic_horizons_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_seismic_horizons_line_id"), ["line_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("seismic_horizons", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_seismic_horizons_line_id"))
        batch_op.drop_index(batch_op.f("ix_seismic_horizons_id"))
    op.drop_table("seismic_horizons")
    with op.batch_alter_table("seismic_lines", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_seismic_lines_project_id"))
        batch_op.drop_index(batch_op.f("ix_seismic_lines_id"))
    op.drop_table("seismic_lines")
