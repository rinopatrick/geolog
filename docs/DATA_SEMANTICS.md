# Data Semantics v1

Responses from `/api/log-runs/{id}/data` and `/data-decimated` now carry a
`semantics` block. The stored curves are never rewritten; corrections happen on
read through `backend/semantics.py`.

## Resolution order

1. **Alias** — a `CurveAlias` row maps a raw mnemonic to a canonical one.
2. **Unit** — known units are converted to the well's `unit_system`.
3. **Canonical mnemonic** — used as the output key.

If two curves resolve to the same canonical name, both keep their raw names and
the response includes an `alias_collision` warning. Nothing is guessed.

## Well target

`unit_system` is `field` (default) or `si`. It is editable on the well
create/edit form and through `PUT /api/wells/{wid}`.

- field: ft, us/ft, g/cc, v/v, ohm.m, psi, md, °F, in
- SI: m, us/m, kg/m3, v/v, ohm.m, MPa, m2, °C, mm

Unknown units are left unchanged with a warning.

## Depth control points

`GET/PUT/DELETE /api/log-runs/{lr_id}/depth-control-points` reads or replaces
the ordered `(md, corrected_depth)` points. At least two points are required;
MD must be strictly increasing. Interpolation is linear. Outside the control
range, the nearest segment is extended linearly. Legacy `shift`/`stretch` is
used only when no control points exist and is reported as `legacy_shift`.

`GET/POST /api/log-runs/{lr_id}/depth-shift` remains for compatibility.

## Response shape

```json
{
  "GR": [10.0, 20.0],
  "DEPTH": [1000.0, 1001.0],
  "TVD": [1000.0, 1001.0],
  "semantics": {
    "version": "data-semantics-v1",
    "unit_system": "field",
    "depth_source": "control_points",
    "depth_unit_from": "ft",
    "depth_unit_to": "ft",
    "input_hash": "…",
    "aliases": [{"raw": "GAMMA", "name": "GR", "canonical": "GR", "unit_from": "GAPI", "unit_to": "GAPI"}],
    "warnings": []
  }
}
```

`TVD` is interpolated from `DeviationSurvey`. Without a survey, TVD equals MD and
a warning is returned.

## Compute endpoints

The shared helper is used by the log-run data endpoints, advanced QC, unified
saturation (`compute-sw`), permeability, dual-water, VCL models, multimineral
and permeability-multi. They therefore see the same aliases, units and corrected
MD as the viewer. Curve-editing/export endpoints that intentionally operate on
stored values remain direct readers; they are listed in the migration backlog.

## UI

- Well create/edit: Field or SI target.
- Depth Shift card: **Control Points** opens a one-pair-per-line editor.
- Viewer toolbar: `CORRECTED` / `SI UNITS` badge with a tooltip listing the
  semantics version, source and warnings.
- `TVD` is present in the data payload for overlays/exports; a viewer depth-axis
  toggle is still pending because tops/zones are stored in MD.
