"""core/SCAL data model

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-21 15:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _index(table, name, cols, unique=False):
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.create_index(batch_op.f(name), cols, unique=unique)

def upgrade() -> None:
    op.create_table(
        "core_datasets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("imported_by", sa.String(length=120), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("core_datasets", "ix_core_datasets_id", ["id"])
    _index("core_datasets", "ix_core_datasets_well_id", ["well_id"])
    _index("core_datasets", "ix_core_datasets_status", ["status"])

    op.create_table(
        "rock_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("rock_types", "ix_rock_types_id", ["id"])
    _index("rock_types", "ix_rock_types_well_id", ["well_id"])

    op.create_table(
        "core_plugs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("rock_type_id", sa.Integer(), nullable=True),
        sa.Column("plug_name", sa.String(length=120), nullable=False),
        sa.Column("depth_md", sa.Float(), nullable=False),
        sa.Column("depth_tvd", sa.Float(), nullable=True),
        sa.Column("formation", sa.String(length=200), nullable=True),
        sa.Column("lithology", sa.String(length=200), nullable=True),
        sa.Column("porosity", sa.Float(), nullable=True),
        sa.Column("perm_air", sa.Float(), nullable=True),
        sa.Column("perm_klin", sa.Float(), nullable=True),
        sa.Column("grain_density", sa.Float(), nullable=True),
        sa.Column("fluid_saturation", sa.Float(), nullable=True),
        sa.Column("plug_type", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["core_datasets.id"]),
        sa.ForeignKeyConstraint(["rock_type_id"], ["rock_types.id"]),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("well_id", "plug_name", "depth_md", name="uq_core_plug_identity"),
    )
    _index("core_plugs", "ix_core_plugs_id", ["id"])
    _index("core_plugs", "ix_core_plugs_dataset_id", ["dataset_id"])
    _index("core_plugs", "ix_core_plugs_well_id", ["well_id"])
    _index("core_plugs", "ix_core_plugs_rock_type_id", ["rock_type_id"])

    op.create_table(
        "core_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plug_id", sa.Integer(), nullable=False),
        sa.Column("measurement_type", sa.String(length=50), nullable=False),
        sa.Column("method", sa.String(length=80), nullable=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=True),
        sa.Column("quality", sa.String(length=20), nullable=True),
        sa.Column("lab", sa.String(length=200), nullable=True),
        sa.Column("sample_date", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["plug_id"], ["core_plugs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("core_measurements", "ix_core_measurements_id", ["id"])
    _index("core_measurements", "ix_core_measurements_plug_id", ["plug_id"])
    _index("core_measurements", "ix_core_measurements_measurement_type", ["measurement_type"])

    op.create_table(
        "capillary_pressure",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plug_id", sa.Integer(), nullable=False),
        sa.Column("test_type", sa.String(length=30), nullable=True),
        sa.Column("sigma", sa.Float(), nullable=True),
        sa.Column("cos_theta", sa.Float(), nullable=True),
        sa.Column("points_json", sa.Text(), nullable=True),
        sa.Column("quality", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["plug_id"], ["core_plugs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("capillary_pressure", "ix_capillary_pressure_id", ["id"])
    _index("capillary_pressure", "ix_capillary_pressure_plug_id", ["plug_id"])

    op.create_table(
        "relative_perm",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plug_id", sa.Integer(), nullable=False),
        sa.Column("points_json", sa.Text(), nullable=True),
        sa.Column("method", sa.String(length=80), nullable=True),
        sa.Column("quality", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["plug_id"], ["core_plugs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("relative_perm", "ix_relative_perm_id", ["id"])
    _index("relative_perm", "ix_relative_perm_plug_id", ["plug_id"])

    op.create_table(
        "core_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plug_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("scale", sa.String(length=100), nullable=True),
        sa.Column("orientation", sa.String(length=50), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["plug_id"], ["core_plugs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("core_photos", "ix_core_photos_id", ["id"])
    _index("core_photos", "ix_core_photos_plug_id", ["plug_id"])

    op.create_table(
        "thin_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plug_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["plug_id"], ["core_plugs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("thin_sections", "ix_thin_sections_id", ["id"])
    _index("thin_sections", "ix_thin_sections_plug_id", ["plug_id"])

    op.create_table(
        "flow_units",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("cluster_index", sa.Integer(), nullable=False),
        sa.Column("fzi_min", sa.Float(), nullable=True),
        sa.Column("fzi_max", sa.Float(), nullable=True),
        sa.Column("rock_type_id", sa.Integer(), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["rock_type_id"], ["rock_types.id"]),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("flow_units", "ix_flow_units_id", ["id"])
    _index("flow_units", "ix_flow_units_well_id", ["well_id"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("contact_type", sa.String(length=20), nullable=True),
        sa.Column("depth", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("contacts", "ix_contacts_id", ["id"])
    _index("contacts", "ix_contacts_well_id", ["well_id"])
    _index("contacts", "ix_contacts_zone_id", ["zone_id"])

    op.create_table(
        "saturation_height_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("rock_type_id", sa.Integer(), nullable=True),
        sa.Column("model_type", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("parameters_json", sa.Text(), nullable=True),
        sa.Column("r2", sa.Float(), nullable=True),
        sa.Column("residual", sa.Float(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["rock_type_id"], ["rock_types.id"]),
        sa.ForeignKeyConstraint(["well_id"], ["wells.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("saturation_height_models", "ix_saturation_height_models_id", ["id"])
    _index("saturation_height_models", "ix_saturation_height_models_well_id", ["well_id"])
    _index("saturation_height_models", "ix_saturation_height_models_rock_type_id", ["rock_type_id"])
    _index("saturation_height_models", "ix_saturation_height_models_status", ["status"])

def downgrade() -> None:
    for table, indexes in [
        ("saturation_height_models", ["ix_saturation_height_models_id", "ix_saturation_height_models_well_id", "ix_saturation_height_models_rock_type_id", "ix_saturation_height_models_status"]),
        ("contacts", ["ix_contacts_id", "ix_contacts_well_id", "ix_contacts_zone_id"]),
        ("flow_units", ["ix_flow_units_id", "ix_flow_units_well_id"]),
        ("thin_sections", ["ix_thin_sections_id", "ix_thin_sections_plug_id"]),
        ("core_photos", ["ix_core_photos_id", "ix_core_photos_plug_id"]),
        ("relative_perm", ["ix_relative_perm_id", "ix_relative_perm_plug_id"]),
        ("capillary_pressure", ["ix_capillary_pressure_id", "ix_capillary_pressure_plug_id"]),
        ("core_measurements", ["ix_core_measurements_id", "ix_core_measurements_plug_id", "ix_core_measurements_measurement_type"]),
        ("core_plugs", ["ix_core_plugs_id", "ix_core_plugs_dataset_id", "ix_core_plugs_well_id", "ix_core_plugs_rock_type_id"]),
        ("rock_types", ["ix_rock_types_id", "ix_rock_types_well_id"]),
        ("core_datasets", ["ix_core_datasets_id", "ix_core_datasets_well_id", "ix_core_datasets_status"]),
    ]:
        with op.batch_alter_table(table, schema=None) as batch_op:
            for index in indexes:
                batch_op.drop_index(batch_op.f(index))
        op.drop_table(table)
