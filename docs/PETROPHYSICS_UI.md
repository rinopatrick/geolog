# Petrophysics workbench UI

Three dense, data-first panels were added to the existing GeoLog shell:

- **Core / SCAL** (`data-view="corescal"`)
- **Geomechanics** (`data-view="geomechanics"`)
- **Image Log** (`data-view="imagelog"`, rebuilt from the earlier synthetic view)

The visual direction came from OpenDesign's `tech-utility` direction (Datadog /
GitHub density) and was constrained to GeoLog's existing tokens: crude-navy
surfaces, amber accent, Geologica UI text and JetBrains Mono numerics. The
reference artifact is [`prototypes/geolog-workbench.html`](../prototypes/geolog-workbench.html).
No marketing hero, glassmorphism, oversized type or generic card grid is used.

## Core / SCAL

Reads `core/datasets`, `core/plugs`, `core/rock-types`, `core/flow-units`,
`core/saturation-height/models`, and plug details (Pc rows).

- Dataset version selector and draft/approved badge.
- Plug table with MD, formation, porosity, air permeability, computed FZI,
  rock type and QC flag.
- Phi–permeability canvas crossplot with FZI reference lines.
- Pc canvas plot for the selected plug.
- Summary strip: PC fit R², flow unit and QC interpretation.
- Actions: CSV import with dry-run preview/conflict resolution, approve dataset, FZI clustering (`k=3`) and J-function fit.
- Saturation-height model selector and `Apply SH` toggle: the Pc panel can switch between the plug Pc curve and a depth–Sw profile.
- Approved datasets are immutable; the UI disables approval after it lands.

## Geomechanics

Reads/writes versioned `geomechanics/models` and `geomechanics/compute`.

- Model selector, calibrated/assumed provenance badges.
- Pressure-profile canvas with Sv, Pp, Shmin, Shmax and the mud-weight window.
- Calibration rows, mud-window and breakout KPIs, model inputs (mud weight,
  Shmax azimuth, Shmin/Shmax gradients), and a draft-only save action.
- Failure-interval table groups contiguous flagged samples and shows BO/MC/HB/DP
  percentages plus sanding CDP.
- PDF export uses the API report endpoint and the browser auth headers.

## Image Log

Reads/writes `image-assets` and `image-assets/{id}/dips`.

- Asset selector with depth/radius metadata and a canvas-rendered unwrapped image.
- Click the image to add `[depth, azimuth]` trace points; `Fit dip` sends the trace
  to the sinusoid fitter and stores a dip pick.
- Pick table with depth, dip, azimuth, R², quality, one-way approval; pick detail
  with a stereonet-style orientation glyph.
- Raster upload (PNG/JPEG/TIFF/BMP) with depth range and radius; DLIS channel
  import remains an API/CLI concern.
- All image requests use authenticated fetch, not unauthenticated `<img>` URLs.
- Edit asset metadata/range/radius and delete an asset with its picks.

## Role gates

Write actions carry `data-role-required="interpreter,admin"` and are disabled for
viewers by the existing role-gate path. Reads remain viewer-accessible.

## Limits

- No bulk editing outside CSV import; no core-photo upload UI yet.
- No DLIS upload UI; use `POST /image-assets/import-dlis`.
- No auto dip picking, image conditioning, aperture or full coverage QC.
- Canvas charts are screening-quality, not print-grade vector figures.
- The OpenDesign HTML is a reference prototype; the app port uses its own CSS
  classes (`px-*`) and live API data.
