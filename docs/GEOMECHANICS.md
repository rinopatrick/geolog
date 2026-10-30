# Geomechanics screening

This is a deterministic screening module, not a 3D finite-element or
wellbore-stability simulator. Every output carries a provenance label:
`measured`, `calibrated`, `correlation`, `assumption` or `not_available`.

## Inputs

One log run with `RHOB` and `DT`; `DTS` and `GR` are optional. Curves pass
through the shared semantics layer (aliases, units, depth correction, TVD).
If `DTS` is missing, Vs uses the Castagna mudrock relation and the result is
labelled a correlation.

Calibration JSON accepts two-point-or-more lists:

```json
{
  "pp":     [[1000, 433], [1010, 437]],
  "shmin":  [[1000, 700], [1010, 707]],
  "shmax":  [[1000, 1100], [1010, 1110]],
  "shmax_azimuth": 30,
  "fracture_planes": [{"strike": 45, "dip": 60}]
}
```

Absolute `Shmin`/`Shmax` are assumptions unless calibration is supplied.
Without `shmax` calibration the response includes a warning and the values are
labelled `assumption`.

## Calculations

- Overburden: `Sv = sum(rho * 0.4335 * dz)` in psi, using TVD in ft.
- Pore pressure: Eaton (`Pp = Sv - (Sv - Phyd) * (DTn/DT)^n`), Bowers, or
  hydrostatic. The normal trend is fitted to shale `DT` when enough points
  exist; otherwise a deterministic fallback is used.
- Elastic: dynamic `E`, `nu`, `G`, `K` from `Vp`, `Vs`, `RHOB`.
- Stresses: far-field tensor from `Sv`, `Shmin`, `Shmax` and azimuth. The
  borehole hoop stress uses a generalized-Kirsch screening approximation from
  the transformed tensor; it is not a full inclined-well solution.
- Mud window: `MW_MIN` from shear breakout, `MW_MAX` from tensile failure;
  `MW` is the requested mud weight (`ppg`).
- Failure indicators: Mohr-Coulomb, Hoek-Brown and Drucker-Prager at the
  far-field effective principal stresses, plus `SAND_CDP` and optional
  fracture-plane slip. `SAND_CDP` is drawdown capacity (reservoir pressure
  minus critical flowing bottomhole pressure from the same shear criterion
  as `MW_MIN`); zero means no drawdown room before shear at the sandface.
- Breakout (`BO`) is true where the current mud weight is below `MW_MIN`.

## API

```text
GET/POST  /api/wells/{wid}/geomechanics/models
GET/PUT   /api/wells/{wid}/geomechanics/models/{id}
POST      /api/wells/{wid}/geomechanics/models/{id}/approve
POST      /api/wells/{wid}/geomechanics/compute
POST      /api/wells/{wid}/geomechanics/breakout-calibration
GET       /api/wells/{wid}/geomechanics/runs
GET       /api/wells/{wid}/geomechanics/report?format=json|csv|pdf
```

`compute` accepts `model_id`, optional `log_run_id`, `start`, `stop`, `step`.
Approved models are immutable; edit by creating a new version.

## Breakout calibration

`breakout-calibration` accepts `{model_id, breakouts: [{depth, width_deg, mud_weight?}], save}`.
It inverts SHmax from the vertical-well Kirsch hoop stress at the breakout edge
using the model Pp/Shmin, Biot coefficient and UCS:
`SHmax = (UCS + Pw + alpha*Pp - SHmin*(1-2cos w)) / (1+2cos w)` where `w` is the
full breakout width in degrees. This mirrors the forward model
(`base_max - Pw - alpha*Pp = UCS`) — one `Pw` term, not two. Saving writes the points to
the draft model calibration as `shmax` with `shmax_source=breakout_inversion`.
This is a review aid based on manually entered widths, not image processing.

## Limits

- No 3D stress field, faults, poroelastic coupling or thermal stress.
- Breakout calibration assumes a vertical well and manually entered widths; no
automatic image breakout picking.
- No anisotropic elastic model.
- PDF is a compact summary table, not a full engineering report.
