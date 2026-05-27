"""Database models for well log viewer."""
import datetime
from sqlalchemy import Column, Integer, Float, String, Text, Date, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
try:
    from database import Base
except ImportError:
    from backend.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    field_name = Column(String(200), default="")
    operator = Column(String(200), default="")
    country = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    wells = relationship("Well", back_populates="project", cascade="all, delete-orphan")


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
    operator = Column(String(200), default="")
    field_name = Column(String(200), default="")
    spud_date = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("Project", back_populates="wells")
    log_runs = relationship("LogRun", back_populates="well", cascade="all, delete-orphan")
    formation_tops = relationship("FormationTop", back_populates="well", cascade="all, delete-orphan")
    zones = relationship("Zone", back_populates="well", cascade="all, delete-orphan")
    dst_tests = relationship("DSTTest", back_populates="well", cascade="all, delete-orphan")
    rft_points = relationship("RFTPoint", back_populates="well", cascade="all, delete-orphan")
    completion_data = relationship("CompletionData", back_populates="well", cascade="all, delete-orphan")


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
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

    well = relationship("Well", back_populates="log_runs")
    curve_data = relationship("CurveData", back_populates="log_run", cascade="all, delete-orphan")


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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    well = relationship("Well", back_populates="formation_tops")


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    depth = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    annotation_type = Column(String(50), default="note")  # note, flag, zone
    color = Column(String(20), default="#f39c12")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    well = relationship("Well", back_populates="zones")


class CorrelationMarker(Base):
    __tablename__ = "correlation_markers"

    id = Column(Integer, primary_key=True, index=True)
    well_a_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    well_b_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    a_depth = Column(Float, nullable=False)
    b_depth = Column(Float, nullable=False)
    label = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class CorrelationProfile(Base):
    __tablename__ = "correlation_profiles"

    id = Column(Integer, primary_key=True, index=True)
    well_a_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    well_b_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    curve = Column(String(50), default="GR")
    depth_shift = Column(Float, default=0.0)
    stretch = Column(Float, default=1.0)
    snap_to_tops = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    well = relationship("Well")


class LogRunDepthShift(Base):
    __tablename__ = "log_run_depth_shifts"

    id = Column(Integer, primary_key=True, index=True)
    log_run_id = Column(Integer, ForeignKey("log_runs.id"), nullable=False, unique=True)
    shift = Column(Float, default=0.0)
    stretch = Column(Float, default=1.0)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    log_run = relationship("LogRun")


class CurveAlias(Base):
    __tablename__ = "curve_aliases"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    original_mnemonic = Column(String(50), nullable=False)
    alias_mnemonic = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    well = relationship("Well")


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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class User(Base):
    """Multi-user roles for enterprise access control."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(200), default="")
    role = Column(String(50), default="interpreter")  # admin, interpreter, viewer
    token = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
