"""
LAS (Log ASCII Standard) file parser for oil & gas well log data.

Supports LAS 2.0 format — the industry standard for wireline log data.
Parses: version, well info, curve definitions, parameters, and data.
"""
import re
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, TextIO
import io


# Normalize vendor mnemonics into canonical families used by the app
CURVE_ALIASES = {
    # Depth/index
    'DEPTH': 'DEPT',

    # Caliper
    'CALI': 'CAL',
    'HCAL': 'CAL',
    'DCAL': 'CAL',

    # Gamma Ray family
    'GRGC': 'GR',       # KGS: GR corrected
    'CGR': 'GR',        # Corrected GR
    'SGR': 'GR',        # Spectral GR

    # Resistivity family (canonical deep target)
    'RESD': 'RT',
    'ILD': 'RILD',
    'RILD': 'RILD',
    'RILM': 'RILM',
    'RES': 'RT',
    'CILD': 'RT',       # KGS: Conductivity converted
    'CILM': 'RILM',     # KGS: Medium conductivity
    'RLL3': 'RLL3',
    'RXORT': 'RXO',

    # Sonic family
    'DTP': 'DT',
    'DT35': 'DT',       # KGS: DT variant
    'SPOR': 'DT',       # KGS: Sonic porosity (proxy)

    # Density family
    'DEN': 'RHOB',      # KGS: Density
    'DPOR': 'DPOR',     # KGS: Density porosity (separate track)
    'CNLS': 'NPHI',     # KGS: Compensated neutron → neutron porosity
    'NPRL': 'NPHI',     # KGS: Neutron porosity
    'RHOC': 'RHOB',     # Corrected density
    'DGA': 'DGA',       # KGS: Density (gamma-gamma) — keep separate

    # SP family
    'SPCG': 'SP',       # KGS: SP corrected
    'SPRL': 'SP',       # KGS: SP

    # Misc
    'CLDC': 'CAL',      # KGS: Caliper
    'DCOR': 'DRHO',     # KGS: Density correction
    'PDPE': 'PE',       # KGS: Photoelectric
    'DPRL': 'NPHI',     # KGS: Density porosity (neutron proxy)
    'FEFE': 'PE',       # KGS: Iron/PE

    # Common no-op canonical mnemonics (explicit for readability)
    'GR': 'GR',
    'SP': 'SP',
    'SPC': 'SP',
    'CAL': 'CAL',
    'RT': 'RT',
    'RXO': 'RXO',
    'NPHI': 'NPHI',
    'RHOB': 'RHOB',
    'DT': 'DT',
    'PE': 'PE',
    'PEF': 'PE',
    'DRHO': 'DRHO',
    'DPOR': 'DPOR',
    'DGA': 'DGA',
    'MI': 'MI',
    'MN': 'MN',
}

# Additional curve track configs for non-standard canonical names
EXTRA_CURVE_TRACKS = {
    'DPOR': {'track': 3, 'color': '#f39c12', 'scale': (0.45, -0.15), 'unit': 'PU', 'name': 'Density Porosity'},
    'DGA':  {'track': 3, 'color': '#e67e22', 'scale': (1.95, 2.95), 'unit': 'GM/CC', 'name': 'Gamma-Gamma Density'},
    'RLL3': {'track': 2, 'color': '#f39c12', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Laterolog 3'},
    'RILM': {'track': 2, 'color': '#e67e22', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Medium Induction'},
}

DEPTH_CANDIDATES = ('DEPT', 'DEPTH', 'MD', 'TVD')


@dataclass
class LASCurve:
    """Curve definition from ~C section."""
    mnemonic: str       # e.g. "GR", "RHOB", "NPHI"
    unit: str           # e.g. "GAPI", "G/C3", "V/V"
    value: str          # API code or description
    description: str    # full description

    def __repr__(self):
        return f"LASCurve({self.mnemonic}, {self.unit})"


@dataclass
class LASParameter:
    """Parameter from ~P section."""
    mnemonic: str
    unit: str
    value: str
    description: str


@dataclass
class LASWell:
    """Well header info from ~W section."""
    start: float = 0.0
    stop: float = 0.0
    step: float = 0.0
    null: float = -999.25
    well_name: str = ""
    uwi: str = ""           # Unique Well Identifier
    field: str = ""
    location: str = ""
    province: str = ""
    country: str = ""
    operator: str = ""
    service_company: str = ""
    date: str = ""
    api: str = ""

    def __repr__(self):
        return f"LASWell({self.well_name}, {self.uwi})"


@dataclass
class LASFile:
    """Parsed LAS file."""
    version: str = "2.0"
    well: LASWell = field(default_factory=LASWell)
    curves: List[LASCurve] = field(default_factory=list)
    parameters: List[LASParameter] = field(default_factory=list)
    data: Dict[str, np.ndarray] = field(default_factory=dict)
    depth_key: str = ""     # mnemonic of the depth/index curve

    @property
    def depth(self) -> np.ndarray:
        """Get the depth array."""
        if self.depth_key and self.depth_key in self.data:
            return self.data[self.depth_key]
        return np.array([])

    @property
    def curve_names(self) -> List[str]:
        """Get list of curve mnemonics (excluding depth)."""
        return [c.mnemonic for c in self.curves if c.mnemonic != self.depth_key]

    def get_curve(self, mnemonic: str) -> Optional[np.ndarray]:
        """Get curve data by mnemonic."""
        return self.data.get(mnemonic)

    def to_dict(self) -> dict:
        """Serialize for JSON response."""
        return {
            "version": self.version,
            "well": {
                "name": self.well.well_name,
                "uwi": self.well.uwi,
                "field": self.well.field,
                "location": self.well.location,
                "operator": self.well.operator,
                "date": self.well.date,
                "start": self.well.start,
                "stop": self.well.stop,
                "step": self.well.step,
                "null": self.well.null,
            },
            "curves": [
                {
                    "mnemonic": c.mnemonic,
                    "unit": c.unit,
                    "description": c.description,
                }
                for c in self.curves
            ],
            "parameters": [
                {"mnemonic": p.mnemonic, "value": p.value, "unit": p.unit}
                for p in self.parameters
            ],
            "depth_key": self.depth_key,
            "num_points": len(self.depth),
        }


class LASParser:
    """
    Parse LAS 2.0/3.0 files.

    LAS format sections:
        ~V - Version info
        ~W - Well info (start, stop, step, null, well name, etc.)
        ~C - Curve definitions
        ~P - Parameters
        ~A - Data (ASCII)
        ~O - Other (comments)

    Also handles non-standard sections (KGS, IQ, Tops, etc.)
    and comma-delimited LAS 3.0 files.
    """

    # Regex to parse a LAS line: mnemonic.unit value : description
    LINE_RE = re.compile(
        r'^\s*(?P<mnemonic>[A-Za-z0-9_\-]+)'      # mnemonic (letters, digits, underscore, dash — NO dots)
        r'\s*(?:\.(?P<unit>[^\s:]*))?'            # optional .unit (supports "MNEM.UNIT" and "MNEM .UNIT")
        r'\s*(?P<value>[^:]*)'                     # optional/empty value before colon
        r'(?::\s*(?P<description>.*))?$'           # optional : description
    )

    @staticmethod
    def parse_file(filepath: str) -> LASFile:
        """Parse a LAS file from disk."""
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return LASParser.parse(f)

    @staticmethod
    def parse_string(content: str) -> LASFile:
        """Parse a LAS file from string content."""
        return LASParser.parse(io.StringIO(content))

    @staticmethod
    def _canonical_mnemonic(mnemonic: str) -> str:
        m = (mnemonic or '').strip().upper()
        return CURVE_ALIASES.get(m, m)

    @staticmethod
    def parse(f: TextIO) -> LASFile:
        """Parse a LAS file from a file-like object."""
        result = LASFile()
        current_section = None
        in_curve_section = False   # True only while inside ~C section
        data_lines = []
        wrap = False
        delimiter = None  # None = whitespace (default), ',' = comma, '\t' = tab

        for line in f:
            line = line.rstrip('\n\r')

            # Skip empty lines and comments
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            # Section header — ANY ~X line ends the previous section
            if stripped.startswith('~'):
                section_char = stripped[1].upper() if len(stripped) > 1 else ''
                if section_char == 'V':
                    current_section = 'version'
                elif section_char == 'W':
                    current_section = 'well'
                elif section_char == 'C':
                    current_section = 'curves'
                    in_curve_section = True
                elif section_char == 'P':
                    current_section = 'parameters'
                    in_curve_section = False
                elif section_char == 'A':
                    current_section = 'data'
                    in_curve_section = False
                    if 'WRAP' in stripped.upper() or 'YES' in stripped.upper():
                        wrap = True
                elif section_char == 'O':
                    current_section = 'other'
                    in_curve_section = False
                else:
                    # Non-standard section (Tops, IQ, Geo_Report, etc.)
                    # Treat as unknown — don't continue parsing as curves
                    current_section = 'unknown'
                    in_curve_section = False
                continue

            # Parse based on current section
            if current_section == 'data':
                data_lines.append(stripped)
            elif current_section in ('version', 'well', 'curves', 'parameters'):
                match = LASParser.LINE_RE.match(stripped)
                if match:
                    mnemonic = LASParser._canonical_mnemonic(match.group('mnemonic'))
                    unit = (match.group('unit') or '').strip()
                    value = (match.group('value') or '').strip()
                    description = (match.group('description') or '').strip()

                    if current_section == 'version':
                        if mnemonic.upper() == 'VERS':
                            result.version = value
                        elif mnemonic.upper() == 'WRAP':
                            wrap = value.upper() == 'YES'
                        elif mnemonic.upper() == 'DLM':
                            # LAS 3.0 delimiter
                            dl = value.strip().upper()
                            if dl == 'COMMA':
                                delimiter = ','
                            elif dl == 'TAB':
                                delimiter = '\t'

                    elif current_section == 'well':
                        LASParser._parse_well_field(result.well, mnemonic, value)

                    elif current_section == 'curves' and in_curve_section:
                        # Only accept valid curve mnemonics:
                        # must start with a letter (not numeric-only)
                        mnem_upper = mnemonic.upper()
                        if mnem_upper and mnem_upper[0].isalpha():
                            # Deduplicate: skip if canonical name already exists
                            existing = [c.mnemonic for c in result.curves]
                            if mnem_upper not in existing:
                                result.curves.append(LASCurve(
                                    mnemonic=mnem_upper,
                                    unit=unit,
                                    value=value,
                                    description=description,
                                ))

                    elif current_section == 'parameters':
                        result.parameters.append(LASParameter(
                            mnemonic=mnemonic,
                            unit=unit,
                            value=value,
                            description=description,
                        ))

        # Set depth key with fallback: DEPT/DEPTH/MD/TVD, else first curve
        if result.curves:
            mnems = [c.mnemonic for c in result.curves]
            result.depth_key = next((m for m in DEPTH_CANDIDATES if m in mnems), result.curves[0].mnemonic)

        # Parse data section
        LASParser._parse_data(result, data_lines, wrap, delimiter)

        return result

    @staticmethod
    def _parse_well_field(well: LASWell, mnemonic: str, value: str):
        """Map ~W fields to LASWell attributes."""
        mapping = {
            'STRT': 'start',
            'STOP': 'stop',
            'STEP': 'step',
            'NULL': 'null',
            'WELL': 'well_name',
            'UWI': 'uwi',
            'UWI1': 'uwi',
            'FLD': 'field',
            'LOC': 'location',
            'PROV': 'province',
            'CTRY': 'country',
            'OPER': 'operator',
            'SRVC': 'service_company',
            'DATE': 'date',
            'API': 'api',
        }
        attr = mapping.get(mnemonic.upper())
        if attr:
            if attr in ('start', 'stop', 'step', 'null'):
                try:
                    setattr(well, attr, float(value))
                except ValueError:
                    pass
            else:
                setattr(well, attr, value)

    @staticmethod
    def _parse_data(las: LASFile, data_lines: List[str], wrap: bool, delimiter=None):
        """Parse the ~A data section into numpy arrays."""
        num_curves = len(las.curves)
        if num_curves == 0 or not data_lines:
            return

        def split_line(line: str) -> list:
            """Split a data line using the detected delimiter or whitespace."""
            if delimiter:
                return line.split(delimiter)
            return line.split()

        if wrap:
            # Wrapped format: data continues on next line
            all_values = []
            current_row = []
            for line in data_lines:
                values = split_line(line)
                current_row.extend(values)
                if len(current_row) >= num_curves:
                    all_values.append(current_row[:num_curves])
                    current_row = current_row[num_curves:]
        else:
            all_values = []
            for line in data_lines:
                values = split_line(line)
                if len(values) >= num_curves:
                    all_values.append(values[:num_curves])

        if not all_values:
            return

        # Convert to numpy arrays
        for i, curve in enumerate(las.curves):
            try:
                col_data = []
                for row in all_values:
                    try:
                        col_data.append(float(row[i]))
                    except (ValueError, IndexError):
                        col_data.append(las.well.null)
                arr = np.array(col_data, dtype=np.float64)
                # Replace null sentinels with NaN (supports exact and float-noise matches)
                if np.isfinite(las.well.null):
                    arr[np.isclose(arr, las.well.null, rtol=0.0, atol=1e-9)] = np.nan
                las.data[curve.mnemonic] = arr
            except Exception:
                las.data[curve.mnemonic] = np.full(len(all_values), np.nan)


# ─── Common curve mnemonics and their standard track assignments ────

CURVE_TRACKS = {
    # Track 1: GR, SP, CAL
    'GR':   {'track': 1, 'color': '#2ecc71', 'scale': (0, 150), 'unit': 'GAPI', 'name': 'Gamma Ray'},
    'SGR':  {'track': 1, 'color': '#27ae60', 'scale': (0, 150), 'unit': 'GAPI', 'name': 'Spectral GR'},
    'CGR':  {'track': 1, 'color': '#1abc9c', 'scale': (0, 150), 'unit': 'GAPI', 'name': 'Corrected GR'},
    'SP':   {'track': 1, 'color': '#3498db', 'scale': (-200, 200), 'unit': 'MV', 'name': 'Spontaneous Potential'},
    'CAL':  {'track': 1, 'color': '#e67e22', 'scale': (6, 16), 'unit': 'IN', 'name': 'Caliper'},
    'HCAL': {'track': 1, 'color': '#e67e22', 'scale': (6, 16), 'unit': 'IN', 'name': 'Hole Caliper'},
    'BS':   {'track': 1, 'color': '#d35400', 'scale': (6, 16), 'unit': 'IN', 'name': 'Bit Size'},

    # Track 2: Resistivity (log scale)
    'RT':   {'track': 2, 'color': '#e74c3c', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Deep Resistivity'},
    'RXO':  {'track': 2, 'color': '#c0392b', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Flushed Zone Resistivity'},
    'RILD': {'track': 2, 'color': '#e74c3c', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Deep Induction'},
    'RILM': {'track': 2, 'color': '#e67e22', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Medium Induction'},
    'RLL3': {'track': 2, 'color': '#f39c12', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Laterolog 3'},
    'RLLS': {'track': 2, 'color': '#f1c40f', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Shallow Laterolog'},
    'MSFL': {'track': 2, 'color': '#f39c12', 'scale': (0.2, 2000), 'log': True, 'unit': 'OHMM', 'name': 'Micro-Spherically Focused'},

    # Track 3: Porosity
    'NPHI': {'track': 3, 'color': '#3498db', 'scale': (0.45, -0.15), 'unit': 'V/V', 'name': 'Neutron Porosity'},
    'RHOB': {'track': 3, 'color': '#e74c3c', 'scale': (1.95, 2.95), 'unit': 'G/C3', 'name': 'Bulk Density'},
    'RHOZ': {'track': 3, 'color': '#e74c3c', 'scale': (1.95, 2.95), 'unit': 'G/C3', 'name': 'Density (Z-axis)'},
    'DT':   {'track': 3, 'color': '#9b59b6', 'scale': (140, 40), 'unit': 'US/F', 'name': 'Sonic Transit Time'},
    'DTC':  {'track': 3, 'color': '#9b59b6', 'scale': (140, 40), 'unit': 'US/F', 'name': 'Compressional Slowness'},
    'DTS':  {'track': 3, 'color': '#8e44ad', 'scale': (300, 50), 'unit': 'US/F', 'name': 'Shear Slowness'},
    'PEF':  {'track': 3, 'color': '#1abc9c', 'scale': (0, 10), 'unit': 'B/E', 'name': 'Photoelectric Factor'},
    'DRHO': {'track': 3, 'color': '#95a5a6', 'scale': (-0.2, 0.2), 'unit': 'G/C3', 'name': 'Density Correction'},

    # Track 4: Saturation / Formation
    'SW':    {'track': 4, 'color': '#3498db', 'scale': (0, 1), 'unit': 'V/V', 'name': 'Water Saturation'},
    'PHIE':  {'track': 4, 'color': '#2ecc71', 'scale': (0, 0.4), 'unit': 'V/V', 'name': 'Effective Porosity'},
    'PHIT':  {'track': 4, 'color': '#27ae60', 'scale': (0, 0.4), 'unit': 'V/V', 'name': 'Total Porosity'},
    'VSH':   {'track': 4, 'color': '#e67e22', 'scale': (0, 1), 'unit': 'V/V', 'name': 'Shale Volume'},
    'BVW':   {'track': 4, 'color': '#2980b9', 'scale': (0, 0.4), 'unit': 'V/V', 'name': 'Bulk Volume Water'},
    'PERM':  {'track': 4, 'color': '#16a085', 'scale': (0.01, 10000), 'log': True, 'unit': 'MD', 'name': 'Permeability'},
}

# Track layout defaults
TRACK_CONFIG = {
    1: {'name': 'GR / SP / CAL', 'width': 80},
    2: {'name': 'Resistivity', 'width': 80},
    3: {'name': 'Porosity', 'width': 80},
    4: {'name': 'Saturation', 'width': 80},
}

# Merge extra tracks into CURVE_TRACKS at module load
CURVE_TRACKS.update(EXTRA_CURVE_TRACKS)
