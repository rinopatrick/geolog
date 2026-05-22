"""Pydantic schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: str = ""
    field_name: str = ""
    operator: str = ""
    country: str = ""

class ProjectCreate(ProjectBase): pass
class ProjectUpdate(ProjectBase):
    name: Optional[str] = None

class ProjectOut(ProjectBase):
    id: int
    created_at: datetime
    well_count: Optional[int] = 0
    class Config:
        from_attributes = True


class WellBase(BaseModel):
    name: str = Field(..., max_length=200)
    uwi: str = ""
    api_number: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation: Optional[float] = None
    total_depth: Optional[float] = None
    depth_unit: str = "FT"
    operator: str = ""
    field_name: str = ""

class WellCreate(WellBase):
    project_id: int

class WellUpdate(BaseModel):
    name: Optional[str] = None
    uwi: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation: Optional[float] = None
    notes: Optional[str] = None

class WellOut(WellBase):
    id: int
    project_id: int
    created_at: datetime
    log_run_count: Optional[int] = 0
    class Config:
        from_attributes = True


class LogRunOut(BaseModel):
    id: int
    well_id: int
    run_number: int
    filename: str
    las_version: str
    start_depth: Optional[float] = None
    stop_depth: Optional[float] = None
    step: Optional[float] = None
    num_points: int = 0
    curves_json: str = "[]"
    uploaded_at: datetime
    class Config:
        from_attributes = True


class CurveOut(BaseModel):
    id: int
    mnemonic: str
    unit: str
    description: str
    num_points: int
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    class Config:
        from_attributes = True


class FormationTopBase(BaseModel):
    formation_name: str
    depth: float
    depth_unit: str = "FT"
    color: str = "#888888"
    lithology: str = ""
    notes: str = ""

class FormationTopCreate(FormationTopBase):
    well_id: int

class FormationTopOut(FormationTopBase):
    id: int
    well_id: int
    class Config:
        from_attributes = True


class CurveDataRequest(BaseModel):
    curve_mnemonics: List[str]
    start_depth: Optional[float] = None
    stop_depth: Optional[float] = None
    step: Optional[int] = 1  # decimation factor
