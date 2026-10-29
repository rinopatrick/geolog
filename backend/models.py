"""Database models for well log viewer."""
from sqlalchemy import Column, Integer, Float, String, Text, Date, DateTime, ForeignKey, LargeBinary, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
try:
    from database import Base
except ImportError:
    from backend.database import Base

try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    field_name = Column(String(200), default="")
    operator = Column(String(200), default="")
    country = Column(String(100), default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    wells = relationship("Well", back_populates="project", cascade="all, delete-orphan")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")


class Well(Base):
    __tablename__ = "wells"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(200), nullable=False)
    uwi = Column(String(100), default="")       # Unique Well Identifier
    api_number = Column(String(100), default="") # API number
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    elevation = Column(Float, nullable=True)     # kelly bushing elevation
    total_depth = Column(Float, nullable=True)   # TD in feet or meters
    depth_unit = Column(String(10), default="FT")  # FT or M
    unit_system = Column(String(10), nullable=False, default="field", server_default="field")  # field | si
    operator = Column(String(200), default="")
    field_name = Column(String(200), default="")
    spud_date = Column(String(50), default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="wells")
    log_runs = relationship("LogRun", back_populates="well", cascade="all, delete-orphan")
    formation_tops = relationship("FormationTop", back_populates="well", cascade="all, delete-orphan")
    zones = relationship("Zone", back_populates="well", cascade="all, delete-orphan")
    dst_tests = relationship("DSTTest", back_populates="well", cascade="all, delete-orphan")
    rft_points = relationship("RFTPoint", back_populates="well", cascade="all, delete-orphan")
    completion_data = relationship("CompletionData", back_populates="well", cascade="all, delete-orphan")
    core_datasets = relationship("CoreDataset", back_populates="well", cascade="all, delete-orphan")
    rock_types = relationship("RockType", back_populates="well", cascade="all, delete-orphan")
    flow_units = relationship("FlowUnit", back_populates="well", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="well", cascade="all, delete-orphan")
    saturation_height_models = relationship("SaturationHeightModel", back_populates="well", cascade="all, delete-orphan")
    members = relationship("WellMember", back_populates="well", cascade="all, delete-orphan")
    geomechanics_models = relationship("GeomechanicsModel", back_populates="well", cascade="all, delete-orphan")
    image_assets = relationship("ImageAsset", back_populates="well", cascade="all, delete-orphan")
    core_depth_matches = relationship("CoreDepthMatch", back_populates="well", cascade="all, delete-orphan")


class LogRun(Base):
    __tablename__ = "log_runs"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    run_number = Column(Integer, default=1)
    filename = Column(String(500), nullable=False)
    las_version = Column(String(10), default="2.0")
    start_depth = Column(Float, nullable=True)
    stop_depth = Column(Float, nullable=True)
    step = Column(Float, nullable=True)
    null_value = Column(Float, default=-999.25)
    num_points = Column(Integer, default=0)
    curves_json = Column(Text, default="[]")  # JSON array of curve definitions
    parameters_json = Column(Text, default="[]")
    uploaded_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="log_runs")
    curve_data = relationship("CurveData", back_populates="log_run", cascade="all, delete-orphan")
    depth_control_points = relationship("DepthControlPoint", back_populates="log_run", cascade="all, delete-orphan")
    nmr_inversions = relationship("NmrInversion", back_populates="log_run", cascade="all, delete-orphan")



class DepthControlPoint(Base):
    """Ordered MD -> corrected-depth control points for one log run."""
    __tablename__ = "depth_control_points"

    id = Column(Integer, primary_key=True, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=False, index=True)
    md = Column(Float, nullable=False)
    corrected_depth = Column(Float, nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    log_run = relationship("LogRun", back_populates="depth_control_points")
    __table_args__ = (
        UniqueConstraint("log_run_id", "md", name="uq_depth_control_points_run_md"),
    )


class NmrInversion(Base):
    """One T2 inversion result for a log run."""
    __tablename__ = "nmr_inversions"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=False, index=True)
    method = Column(String(50), default="nnls")
    t2_bins_json = Column(Text, default="[]")
    cutoff_ms = Column(Float, default=33.0)
    lambda_value = Column(Float, default=0.1)
    n_depth = Column(Integer, default=0)
    n_bins = Column(Integer, default=0)
    params_hash = Column(String(64), default="")
    engine_version = Column(String(50), default="nmr-v1")
    created_at = Column(DateTime, default=utcnow)

    log_run = relationship("LogRun", back_populates="nmr_inversions")
    distribution = relationship("NmrDistribution", back_populates="inversion", cascade="all, delete-orphan", uselist=False)

class NmrDistribution(Base):
    __tablename__ = "nmr_distributions"

    id = Column(Integer, primary_key=True, index=True)
    inversion_id = Column(Integer, ForeignKey("nmr_inversions.id"), nullable=False, unique=True, index=True)
    n_depth = Column(Integer, default=0)
    n_bins = Column(Integer, default=0)
    depth_binary = Column(LargeBinary, nullable=True)
    amplitudes = Column(LargeBinary, nullable=True)

    inversion = relationship("NmrInversion", back_populates="distribution")

class CurveData(Base):
    __tablename__ = "curve_data"

    id = Column(Integer, primary_key=True, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=False)
    mnemonic = Column(String(50), nullable=False)
    unit = Column(String(50), default="")
    description = Column(Text, default="")
    num_points = Column(Integer, default=0)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    # Store actual data as binary (numpy array serialized)
    data_binary = Column(LargeBinary, nullable=True)

    log_run = relationship("LogRun", back_populates="curve_data")


class FormationTop(Base):
    __tablename__ = "formation_tops"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    formation_name = Column(String(200), nullable=False)
    depth = Column(Float, nullable=False)
    top_depth = Column(Float, nullable=True)
    base_depth = Column(Float, nullable=True)
    depth_unit = Column(String(10), default="FT")
    color = Column(String(20), default="#888888")
    lithology = Column(String(100), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="formation_tops")


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    depth = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    annotation_type = Column(String(50), default="note")  # note, flag, zone
    color = Column(String(20), default="#f39c12")
    created_at = Column(DateTime, default=utcnow)


class DSTTest(Base):
    __tablename__ = "dst_tests"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    test_number = Column(String(100), default="")
    top_depth = Column(Float, nullable=False)
    bottom_depth = Column(Float, nullable=False)
    formation = Column(String(200), default="")
    choke_size = Column(String(100), default="")
    flow_rate = Column(Float, nullable=True)
    shut_in_pressure = Column(Float, nullable=True)
    flowing_pressure = Column(Float, nullable=True)
    temperature = Column(Float, nullable=True)
    permeability = Column(Float, nullable=True)
    skin = Column(Float, nullable=True)
    result = Column(String(200), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="dst_tests")


class RFTPoint(Base):
    __tablename__ = "rft_points"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    depth = Column(Float, nullable=False)
    pressure = Column(Float, nullable=False)
    mobility = Column(Float, nullable=True)
    fluid_type = Column(String(50), default="unknown")
    sample_recovered = Column(String(100), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="rft_points")


class CompletionData(Base):
    __tablename__ = "completion_data"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    depth_top = Column(Float, nullable=False)
    depth_base = Column(Float, nullable=False)
    component_type = Column(String(50), nullable=False)
    size = Column(String(100), default="")
    description = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="completion_data")


class ProductionData(Base):
    __tablename__ = "production_data"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    oil_rate = Column(Float, nullable=True)          # bbl/d
    gas_rate = Column(Float, nullable=True)          # mcf/d
    water_rate = Column(Float, nullable=True)        # bbl/d
    water_cut = Column(Float, nullable=True)         # %
    gor = Column(Float, nullable=True)               # scf/bbl
    bhp = Column(Float, nullable=True)               # psi
    whp = Column(Float, nullable=True)               # psi
    choke_size = Column(Float, nullable=True)        # 64ths
    cumulative_oil = Column(Float, nullable=True)
    cumulative_gas = Column(Float, nullable=True)
    cumulative_water = Column(Float, nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    name = Column(String(200), nullable=False)
    top_depth = Column(Float, nullable=False)
    bottom_depth = Column(Float, nullable=False)
    color = Column(String(20), default="#1f6feb")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    well = relationship("Well", back_populates="zones")


class CorrelationMarker(Base):
    __tablename__ = "correlation_markers"

    id = Column(Integer, primary_key=True, index=True)
    well_a_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    well_b_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    a_depth = Column(Float, nullable=False)
    b_depth = Column(Float, nullable=False)
    label = Column(String(100), default="")
    created_at = Column(DateTime, default=utcnow)


class CorrelationProfile(Base):
    __tablename__ = "correlation_profiles"

    id = Column(Integer, primary_key=True, index=True)
    well_a_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    well_b_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    curve = Column(String(50), default="GR")
    depth_shift = Column(Float, default=0.0)
    stretch = Column(Float, default=1.0)
    snap_to_tops = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class PetroParams(Base):
    """Saved petrophysics parameters + template preset per well."""
    __tablename__ = "petro_params"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, unique=True)
    saturation_model = Column(String(50), default="archie")  # archie / simandoux / indonesian / dual_water
    a = Column(Float, default=1.0)
    m = Column(Float, default=2.0)
    n = Column(Float, default=2.0)
    rw = Column(Float, default=0.1)
    vsh_cutoff = Column(Float, default=0.35)
    phie_cutoff = Column(Float, default=0.10)
    sw_cutoff = Column(Float, default=0.60)
    template = Column(String(50), default="custom")  # sandstone / carbonate / shaly_sand / custom
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    well = relationship("Well")


class LogRunDepthShift(Base):
    __tablename__ = "log_run_depth_shifts"

    id = Column(Integer, primary_key=True, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=False, unique=True)
    shift = Column(Float, default=0.0)
    stretch = Column(Float, default=1.0)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    log_run = relationship("LogRun")


class CurveAlias(Base):
    __tablename__ = "curve_aliases"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    original_mnemonic = Column(String(50), nullable=False)
    alias_mnemonic = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well")


class DeviationSurvey(Base):
    __tablename__ = "deviation_surveys"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    md = Column(Float, nullable=False)
    inc = Column(Float, nullable=False)
    azi = Column(Float, nullable=False)
    tvd = Column(Float, nullable=True)
    northing = Column(Float, nullable=True)
    easting = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well")




class CoreDataset(Base):
    """A versioned, approvable set of core plugs for one well."""
    __tablename__ = "core_datasets"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    version = Column(Integer, default=1)
    status = Column(String(20), default="draft", index=True)
    source = Column(String(200), default="")
    imported_by = Column(String(120), default="")
    imported_at = Column(DateTime, default=utcnow)
    approved_by = Column(String(120), default="")
    approved_at = Column(DateTime, nullable=True)
    input_hash = Column(String(64), default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="core_datasets")
    plugs = relationship("CorePlug", back_populates="dataset", cascade="all, delete-orphan")

class CorePlug(Base):
    __tablename__ = "core_plugs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("core_datasets.id"), nullable=False, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    rock_type_id = Column(Integer, ForeignKey("rock_types.id"), nullable=True, index=True)
    plug_name = Column(String(120), nullable=False)
    depth_md = Column(Float, nullable=False)
    depth_tvd = Column(Float, nullable=True)
    matched_log_md = Column(Float, nullable=True)
    depth_matches = relationship("CoreDepthMatch", back_populates="plug", cascade="all, delete-orphan")
    formation = Column(String(200), default="")
    lithology = Column(String(200), default="")
    porosity = Column(Float, nullable=True)
    perm_air = Column(Float, nullable=True)
    perm_klin = Column(Float, nullable=True)
    grain_density = Column(Float, nullable=True)
    fluid_saturation = Column(Float, nullable=True)
    plug_type = Column(String(50), default="routine")
    source = Column(String(200), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("CoreDataset", back_populates="plugs")
    measurements = relationship("CoreMeasurement", back_populates="plug", cascade="all, delete-orphan")
    capillary_pressure = relationship("CapillaryPressure", back_populates="plug", cascade="all, delete-orphan")
    relative_perm = relationship("RelativePerm", back_populates="plug", cascade="all, delete-orphan")
    photos = relationship("CorePhoto", back_populates="plug", cascade="all, delete-orphan")
    thin_sections = relationship("ThinSection", back_populates="plug", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("well_id", "plug_name", "depth_md", name="uq_core_plug_identity"),
    )

class CoreMeasurement(Base):
    __tablename__ = "core_measurements"

    id = Column(Integer, primary_key=True, index=True)
    plug_id = Column(Integer, ForeignKey("core_plugs.id"), nullable=False, index=True)
    measurement_type = Column(String(50), nullable=False, index=True)
    method = Column(String(80), default="")
    value = Column(Float, nullable=False)
    unit = Column(String(30), default="")
    quality = Column(String(20), default="")
    lab = Column(String(200), default="")
    sample_date = Column(String(40), default="")
    created_at = Column(DateTime, default=utcnow)

    plug = relationship("CorePlug", back_populates="measurements")

class CapillaryPressure(Base):
    __tablename__ = "capillary_pressure"

    id = Column(Integer, primary_key=True, index=True)
    plug_id = Column(Integer, ForeignKey("core_plugs.id"), nullable=False, index=True)
    test_type = Column(String(30), default="drainage")
    sigma = Column(Float, default=72.0)
    cos_theta = Column(Float, default=1.0)
    points_json = Column(Text, default="[]")
    quality = Column(String(20), default="")
    created_at = Column(DateTime, default=utcnow)

    plug = relationship("CorePlug", back_populates="capillary_pressure")

class RelativePerm(Base):
    __tablename__ = "relative_perm"

    id = Column(Integer, primary_key=True, index=True)
    plug_id = Column(Integer, ForeignKey("core_plugs.id"), nullable=False, index=True)
    points_json = Column(Text, default="[]")
    method = Column(String(80), default="")
    quality = Column(String(20), default="")
    created_at = Column(DateTime, default=utcnow)

    plug = relationship("CorePlug", back_populates="relative_perm")

class CorePhoto(Base):
    __tablename__ = "core_photos"

    id = Column(Integer, primary_key=True, index=True)
    plug_id = Column(Integer, ForeignKey("core_plugs.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    caption = Column(Text, default="")
    scale = Column(String(100), default="")
    orientation = Column(String(50), default="")
    checksum = Column(String(64), default="")
    created_at = Column(DateTime, default=utcnow)

    plug = relationship("CorePlug", back_populates="photos")

class ThinSection(Base):
    __tablename__ = "thin_sections"

    id = Column(Integer, primary_key=True, index=True)
    plug_id = Column(Integer, ForeignKey("core_plugs.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    caption = Column(Text, default="")
    description = Column(Text, default="")
    checksum = Column(String(64), default="")
    created_at = Column(DateTime, default=utcnow)

    plug = relationship("CorePlug", back_populates="thin_sections")

class RockType(Base):
    __tablename__ = "rock_types"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    color = Column(String(20), default="#58a6ff")
    description = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="rock_types")

class FlowUnit(Base):
    __tablename__ = "flow_units"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    version = Column(Integer, default=1)
    cluster_index = Column(Integer, nullable=False)
    fzi_min = Column(Float, nullable=True)
    fzi_max = Column(Float, nullable=True)
    rock_type_id = Column(Integer, ForeignKey("rock_types.id"), nullable=True)
    stats_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="flow_units")

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True, index=True)
    contact_type = Column(String(20), default="FWL")
    depth = Column(Float, nullable=False)
    source = Column(String(200), default="")
    confidence = Column(String(20), default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="contacts")

class SaturationHeightModel(Base):
    __tablename__ = "saturation_height_models"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    rock_type_id = Column(Integer, ForeignKey("rock_types.id"), nullable=True, index=True)
    model_type = Column(String(50), nullable=False)
    version = Column(Integer, default=1)
    status = Column(String(20), default="draft", index=True)
    parameters_json = Column(Text, default="{}")
    r2 = Column(Float, nullable=True)
    residual = Column(Float, nullable=True)
    input_hash = Column(String(64), default="")
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    created_by = Column(String(120), default="")
    created_at = Column(DateTime, default=utcnow)
    approved_by = Column(String(120), default="")
    approved_at = Column(DateTime, nullable=True)

    well = relationship("Well", back_populates="saturation_height_models")



class GeomechanicsModel(Base):
    """Versioned screening parameters/calibration for one well and optional zone."""
    __tablename__ = "geomechanics_models"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=True, index=True)
    version = Column(Integer, default=1)
    status = Column(String(20), default="draft", index=True)
    model_type = Column(String(50), default="screening")
    params_json = Column(Text, default="{}")
    calibration_json = Column(Text, default="{}")
    input_hash = Column(String(64), default="")
    created_by = Column(String(120), default="")
    created_at = Column(DateTime, default=utcnow)
    approved_by = Column(String(120), default="")
    approved_at = Column(DateTime, nullable=True)

    well = relationship("Well", back_populates="geomechanics_models")
    runs = relationship("GeomechanicsRun", back_populates="model", cascade="all, delete-orphan")

class GeomechanicsRun(Base):
    __tablename__ = "geomechanics_runs"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("geomechanics_models.id"), nullable=False, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=False, index=True)
    depth_top = Column(Float, nullable=True)
    depth_bottom = Column(Float, nullable=True)
    summary_json = Column(Text, default="{}")
    warnings_json = Column(Text, default="[]")
    provenance_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)

    model = relationship("GeomechanicsModel", back_populates="runs")



class ImageAsset(Base):
    """A conditioned, unwrapped borehole image stored as an artifact."""
    __tablename__ = "image_assets"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=True, index=True)
    image_type = Column(String(50), default="manual")
    source = Column(String(120), default="")
    file_path = Column(Text, nullable=False)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    depth_top = Column(Float, nullable=False)
    depth_bottom = Column(Float, nullable=False)
    azimuth_start = Column(Float, default=0.0)
    azimuth_end = Column(Float, default=360.0)
    borehole_radius = Column(Float, nullable=True)
    status = Column(String(20), default="draft")
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="image_assets")
    dips = relationship("DipPick", back_populates="asset", cascade="all, delete-orphan")

class DipPick(Base):
    __tablename__ = "dip_picks"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("image_assets.id"), nullable=False, index=True)
    depth = Column(Float, nullable=False)
    dip_angle = Column(Float, nullable=False)
    dip_azimuth = Column(Float, nullable=False)
    amplitude = Column(Float, nullable=True)
    r2 = Column(Float, nullable=True)
    quality = Column(String(20), default="")
    method = Column(String(30), default="manual_trace")
    picked_by = Column(String(120), default="")
    approved = Column(Boolean, default=False)
    notes = Column(Text, default="")
    trace_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=utcnow)

    asset = relationship("ImageAsset", back_populates="dips")



class CoreDepthMatch(Base):
    """Staged core-to-log depth match. Apply copies log_md to CorePlug.matched_log_md."""
    __tablename__ = "core_depth_matches"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    plug_id = Column(Integer, ForeignKey("core_plugs.id"), nullable=False, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=False, index=True)
    core_md = Column(Float, nullable=False)
    log_md = Column(Float, nullable=False)
    shift = Column(Float, default=0.0)
    residual = Column(Float, default=0.0)
    method = Column(String(30), default="manual_shift")
    status = Column(String(20), default="proposed", index=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="core_depth_matches")
    plug = relationship("CorePlug", back_populates="depth_matches")



class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String(64), nullable=False, unique=True, index=True)
    subject = Column(String(120), default="")
    reason = Column(String(120), default="")
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, default=utcnow)

class SharedRateBucket(Base):
    """Fixed-window counter used when GEOLOG_STATE_BACKEND=database."""

    __tablename__ = "shared_rate_buckets"

    key = Column(String(255), primary_key=True)
    count = Column(Integer, nullable=False, default=0)
    reset_at = Column(Float, nullable=False, default=0.0)


class SharedRateLock(Base):
    """Account/credential lock shared across app instances."""

    __tablename__ = "shared_rate_locks"

    key = Column(String(255), primary_key=True)
    until = Column(Float, nullable=False, default=0.0)
    failures = Column(Integer, nullable=False, default=0)


class SharedMetricWorker(Base):
    """Per-worker metrics snapshot; readers aggregate every row."""

    __tablename__ = "shared_metric_workers"

    worker_id = Column(String(120), primary_key=True)
    payload = Column(Text, nullable=False, default="{}")
    updated_at = Column(Float, nullable=False, default=0.0)



class SeismicLine(Base):
    """Uploaded SEG-Y line stored under the artifact directory."""

    __tablename__ = "seismic_lines"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    filename = Column(String(255), default="")
    file_path = Column(String(500), nullable=False)
    format_code = Column(Integer, default=5)
    sample_interval_ms = Column(Float, default=0.0)
    samples_per_trace = Column(Integer, default=0)
    trace_count = Column(Integer, default=0)
    trace_headers_path = Column(String(500), default="")
    inline_min = Column(Integer, nullable=True)
    inline_max = Column(Integer, nullable=True)
    crossline_min = Column(Integer, nullable=True)
    crossline_max = Column(Integer, nullable=True)
    amplitude_min = Column(Float, nullable=True)
    amplitude_max = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    horizons = relationship("SeismicHorizon", back_populates="line", cascade="all, delete-orphan")
    faults = relationship("SeismicFault", back_populates="line", cascade="all, delete-orphan")
    fault_links = relationship("SeismicFaultLink", back_populates="line", cascade="all, delete-orphan")
    surfaces = relationship("SeismicSurface", back_populates="line", cascade="all, delete-orphan")



class SeismicHorizon(Base):
    __tablename__ = "seismic_horizons"

    id = Column(Integer, primary_key=True, index=True)
    line_id = Column(Integer, ForeignKey("seismic_lines.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    color = Column(String(20), default="#f0883e")
    mode = Column(String(20), default="line")
    section_value = Column(Integer, nullable=True)
    picks_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=utcnow)

    line = relationship("SeismicLine", back_populates="horizons")



class SeismicFault(Base):
    """Auto-detected fault segments on a SEG-Y section."""

    __tablename__ = "seismic_faults"

    id = Column(Integer, primary_key=True, index=True)
    line_id = Column(Integer, ForeignKey("seismic_lines.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    color = Column(String(20), default="#f85149")
    picks_json = Column(Text, default="[]")
    score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    line = relationship("SeismicLine", back_populates="faults")



class Prospect(Base):
    """A volumetrics/risking calculation anchored to a depth surface."""

    __tablename__ = "prospects"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    line_id = Column(Integer, ForeignKey("seismic_lines.id"), nullable=True)
    surface_id = Column(Integer, ForeignKey("seismic_surfaces.id"), nullable=True)
    name = Column(String(160), nullable=False)
    fluid_type = Column(String(20), default="oil")
    contact_depth_m = Column(Float, nullable=True)
    grv_m3 = Column(Float, nullable=True)
    area_m2 = Column(Float, nullable=True)
    result_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)


class ProspectPortfolio(Base):
    """A saved portfolio calculation over multiple prospects."""

    __tablename__ = "prospect_portfolios"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    inputs_json = Column(Text, default="{}")
    result_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)


class WellSeismicTie(Base):
    """A synthetic-seismogram tie at one inline/crossline location."""

    __tablename__ = "well_seismic_ties"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    line_id = Column(Integer, ForeignKey("seismic_lines.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    inline = Column(Integer, nullable=False)
    crossline = Column(Integer, nullable=False)
    checkshot_json = Column(Text, default="[]")
    result_json = Column(Text, default="{}")
    shift_ms = Column(Float, nullable=True)
    correlation = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class VelocityModel(Base):
    """Project time-depth model for seismic depth conversion."""

    __tablename__ = "velocity_models"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(20), default="constant")
    velocity_m_s = Column(Float, nullable=True)
    layers_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=utcnow)


class SeismicSurface(Base):
    """A gridded time surface built from inline/crossline horizon picks."""

    __tablename__ = "seismic_surfaces"

    id = Column(Integer, primary_key=True, index=True)
    line_id = Column(Integer, ForeignKey("seismic_lines.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    grid_json = Column(Text, default="[]")
    inlines_json = Column(Text, default="[]")
    crosslines_json = Column(Text, default="[]")
    sample_interval_ms = Column(Float, default=0.0)
    inline_spacing_m = Column(Float, nullable=True)
    crossline_spacing_m = Column(Float, nullable=True)
    stats_json = Column(Text, default="{}")
    depth_grid_json = Column(Text, default="[]")
    depth_stats_json = Column(Text, default="{}")
    velocity_model_id = Column(Integer, ForeignKey("velocity_models.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    line = relationship("SeismicLine", back_populates="surfaces")


class SeismicFaultLink(Base):
    """A fault candidate linked across adjacent 3D inline sections."""

    __tablename__ = "seismic_fault_links"

    id = Column(Integer, primary_key=True, index=True)
    line_id = Column(Integer, ForeignKey("seismic_lines.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    color = Column(String(20), default="#f85149")
    points_json = Column(Text, default="[]")
    geometry_json = Column(Text, default="{}")
    polygon_json = Column(Text, default="[]")
    score = Column(Float, nullable=True)
    inline_start = Column(Integer, nullable=True)
    inline_end = Column(Integer, nullable=True)
    crossline_center = Column(Float, nullable=True)
    sample_center = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    line = relationship("SeismicLine", back_populates="fault_links")



class SourceRockAnalysis(Base):
    """Metadata for one stored TOC/VKER calculation."""

    __tablename__ = "source_rock_analyses"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=False, index=True)
    method = Column(String(30), nullable=False, default="passey")
    porosity_mode = Column(String(20), default="sonic")
    lom = Column(Float, nullable=True)
    toc_base = Column(Float, nullable=True)
    rt_base = Column(Float, nullable=True)
    porosity_base = Column(Float, nullable=True)
    toc_curve = Column(String(30), default="TOC")
    vker_curve = Column(String(30), default="VKER")
    stats_json = Column(Text, default="{}")
    warnings_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=utcnow)


class ReportTemplate(Base):
    """Saved section selection for the custom well report."""

    __tablename__ = "report_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, default="")
    config_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class SharedWellState(Base):
    """Opaque per-well state (locks, snapshots, template lock) shared by instances."""

    __tablename__ = "shared_well_state"

    key = Column(String(120), primary_key=True)
    payload = Column(Text, nullable=False, default="null")
    version = Column(Integer, nullable=False, default=0)
    updated_at = Column(Float, nullable=False, default=0.0)


class SharedJob(Base):
    """Durable job record shared by every app instance."""

    __tablename__ = "shared_jobs"

    id = Column(String(64), primary_key=True)
    type = Column(String(80), nullable=False, default="")
    payload = Column(Text, nullable=False, default="{}")
    status = Column(String(20), nullable=False, default="queued", index=True)
    progress = Column(Integer, nullable=False, default=0)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    worker_id = Column(String(120), nullable=True)
    created_at = Column(String(40), nullable=False, default="")
    created_epoch = Column(Float, nullable=False, default=0.0)
    started_at = Column(String(40), nullable=True)
    started_epoch = Column(Float, nullable=True)
    finished_at = Column(String(40), nullable=True)
    finished_epoch = Column(Float, nullable=True)


class AuditLog(Base):
    """Track all user actions for audit trail."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=True)
    action = Column(String(100), nullable=False)  # upload, compute, export, edit, delete
    entity_type = Column(String(50), default="")  # well, top, zone, curve, petro_params
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, default="")  # JSON details of what changed
    user_label = Column(String(100), default="local")  # user identifier
    # Immutable provenance chain
    request_id = Column(String(64), default="")
    auth_subject = Column(String(120), default="")
    auth_role = Column(String(50), default="viewer")
    route_path = Column(String(255), default="")
    method = Column(String(10), default="")
    status_code = Column(Integer, nullable=True)
    payload_hash = Column(String(64), default="")
    prev_hash = Column(String(64), default="")
    entry_hash = Column(String(64), default="")
    created_at = Column(DateTime, default=utcnow)


class User(Base):
    """Multi-user roles for enterprise access control."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(200), default="")
    role = Column(String(50), default="interpreter")  # admin, interpreter, viewer
    # Legacy plaintext column. New secrets are written to token_hash; a row is
    # upgraded and this column cleared on its first successful login.
    token = Column(String(200), default="")
    token_hash = Column(String(255), default="")
    created_at = Column(DateTime, default=utcnow)


class WellMember(Base):
    """Per-well ACL override. A well with no members inherits its project."""

    __tablename__ = "well_members"
    __table_args__ = (
        UniqueConstraint("well_id", "subject", name="uq_well_member_subject"),
    )

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    subject = Column(String(160), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="viewer")
    created_at = Column(DateTime, default=utcnow)

    well = relationship("Well", back_populates="members")


class ProjectMember(Base):
    """Per-project ACL. A project with no members stays open for legacy data."""

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "subject", name="uq_project_member_subject"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    subject = Column(String(160), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="viewer")
    created_at = Column(DateTime, default=utcnow)

    project = relationship("Project", back_populates="members")

