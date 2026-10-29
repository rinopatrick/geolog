"""Add velocity models and surface depth grids.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-10-31 15:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "velocity_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=True),
        sa.Column("velocity_m_s", sa.Float(), nullable=True),
        sa.Column("layers_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_velocity_models_id", "velocity_models", ["id"])
    op.create_index("ix_velocity_models_project_id", "velocity_models", ["project_id"])
    with op.batch_alter_table("seismic_surfaces") as batch:
        batch.add_column(sa.Column("depth_grid_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("depth_stats_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("velocity_model_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_seismic_surfaces_velocity_model_id",
            "velocity_models",
            ["velocity_model_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("seismic_surfaces") as batch:
        batch.drop_constraint("fk_seismic_surfaces_velocity_model_id", type_="foreignkey")
        batch.drop_column("velocity_model_id")
        batch.drop_column("depth_stats_json")
        batch.drop_column("depth_grid_json")
    op.drop_index("ix_velocity_models_project_id", table_name="velocity_models")
    op.drop_index("ix_velocity_models_id", table_name="velocity_models")
    op.drop_table("velocity_models")
