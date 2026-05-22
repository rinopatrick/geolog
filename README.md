# GeoLog — Oil & Gas Well Log Viewer

Open-source, production-style well log viewer for petroleum geophysicists and petrophysicists. Built with FastAPI + SQLite backend and Canvas-based frontend.

![GeoLog Screenshot](screenshot.png)

## Features

### Data Ingest
- **LAS 2.0 parser** with robust field-LAS handling:
  - `MNEM.UNIT` and `MNEM .UNIT` header formats
  - Null sentinel (`-999.25`) → NaN conversion
  - Depth fallback: `DEPT` / `DEPTH` / `MD` / `TVD` → first curve
  - Curve alias normalization: `CALI→CAL`, `RESD→RT`, `ILD→RILD`, `DTP→DT`
- Multi-log-run per well (upload multiple LAS files)
- Formation tops with depth, color, lithology
- Zone picking for interval analysis

### Multi-Track Log Viewer
- **Canvas-rendered** for performance with large datasets
- 4-track layout: GR/SP/CAL | Resistivity (log-scale) | Porosity | Saturation
- Depth ruler with adaptive tick intervals
- Hover readout showing all curve values at cursor depth
- Formation tops overlay with labels
- Scroll-to-zoom, drag-to-pan

### Interpretation Workflow
- **Petrophysics Quicklook**: Vsh (GR), PHIE (NPHI-RHOB), Sw (Archie)
- **Cutoff editor**: Vsh max, PHIE min, Sw max with instant net pay recalculation
- **Reservoir interval table**: zone-by-zone Top/Base/Gross/PHIE/Sw/Vsh
- **Crossplot RHOB-NPHI** with dynamic curve selectors
- **Pickett plot** (log-log Rt vs PHIE) with Archie Sw guide lines
- **M-N plot** with lithology anchors (sandstone/limestone/dolomite)
- **Curve family fallback**: vendor mnemonics (ILD, RESD, RILD) auto-resolve to canonical families

### Well Correlation
- Two-well depth correlation panel
- **Manual marker tie picking**: click A-depth, click B-depth, labeled Δ per marker
- Marker summary table with aggregate shifts
- **Apply Median Shift** / **Apply Mean Shift** from markers
- **AutoTie**: cross-correlation based automatic depth shift with confidence scoring

### QC / Data Quality
- Per-curve: missing %, z-score outlier %, mean, std
- **Reliability tags**: HIGH / MEDIUM / LOW
- Sample size confidence warning for small datasets

### Export
- **Export LAS**: generates LAS 2.0 file from current view
- **Export Summary CSV**: wells, cutoffs, net pay, QC metrics, formation tops
- **Export PNG**: high-res canvas export

## Quick Start

### Prerequisites
- Python 3.9+
- pip

### Setup

```bash
cd geolog-app/backend

# Install dependencies
pip install -r requirements.txt

# Seed demo data (optional)
python seed.py

# Start server
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 in your browser.

### Docker

```bash
docker compose up --build
```

Then open http://localhost:8000.

## Project Structure

```
geolog-app/
├── backend/
│   ├── main.py           # FastAPI app + all API routes
│   ├── las_parser.py     # LAS 2.0 parser with alias normalization
│   ├── models.py         # SQLAlchemy ORM models
│   ├── schemas.py        # Pydantic schemas
│   ├── database.py       # DB engine + session
│   ├── seed.py           # Demo data seeder
│   └── requirements.txt
├── frontend/
│   ├── index.html        # Main HTML shell
│   ├── css/style.css     # Dark theme (GitHub-style)
│   └── js/
│       ├── app.js        # Application logic + all panels
│       └── log-renderer.js  # Canvas-based multi-track renderer
├── data/
│   ├── public_sample.las
│   └── hawkins_01.las    # 800-pt synthetic field LAS
├── Dockerfile
├── docker-compose.yml
├── LICENSE
└── README.md
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET/POST | `/api/projects/` | List / create projects |
| DELETE | `/api/projects/{id}` | Delete project |
| GET/POST | `/api/wells/` | List / create wells |
| GET | `/api/wells/{id}` | Well detail + log runs + tops |
| DELETE | `/api/wells/{id}` | Delete well |
| POST | `/api/wells/{id}/upload-las` | Upload LAS file |
| GET/POST | `/api/wells/{id}/tops` | List / create formation tops |
| GET | `/api/log-runs/{id}/curves` | List curves for a log run |
| POST | `/api/log-runs/{id}/data` | Get curve data (with depth filter) |
| GET | `/api/curve-config` | Standard curve track configurations |
| DELETE | `/api/tops/{id}` | Delete formation top |

## Curve Alias Normalization

The parser normalizes vendor mnemonics to canonical forms:

| Vendor | Canonical | Family |
|--------|-----------|--------|
| DEPTH | DEPT | Depth |
| CALI | CAL | Caliper |
| RESD | RT | Resistivity |
| ILD | RILD | Resistivity |
| DTP | DT | Sonic |

Interpretation panels use **family fallback** — selecting "RT" will also search for `RESD`, `RILD`, `ILD`, `ILM`, `RXO`, `SFLU`, `SFLA`, etc.

## Petrophysics Methods

- **Vsh**: GR linear (Larionov for tertiary rocks)
- **PHIE**: NPHI-RHOB average, corrected for Vsh
- **Sw**: Archie equation: `Sw = (a / (φᵐ × Rt / Rw))^(1/n)`
- **Cutoffs**: user-editable Vsh max, PHIE min, Sw max
- **Net pay**: flag-based with minimum zone thickness filter

## License

MIT License — see [LICENSE](LICENSE).

## Testing

```bash
# Parser tests (no server needed)
python tests/test_parser.py

# Full suite (parser + API — server must be running)
python tests/test_parser.py
```

16 tests: 10 parser (always) + 6 API (needs server).

## Contributing

1. Fork the repo
2. Create a feature branch
3. Submit a PR

For major changes, open an issue first to discuss.
