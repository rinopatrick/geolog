# Prospect volumetrics

A prospect is calculated from a depth-converted `SeismicSurface`:

```
GRV = sum(max(0, contact_depth - top_depth)) * cell_area
cell_area = inline_spacing_m * crossline_spacing_m * inline_step * crossline_step
```

The surface must have `depth_grid`, `inline_spacing_m` and
`crossline_spacing_m`. Time-only surfaces are rejected.

## Monte Carlo

`POST /api/projects/{pid}/prospects` accepts scalar values or triangular ranges:

```json
{
  "name": "Prospect A",
  "surface_id": 3,
  "contact_depth_m": 2450,
  "porosity": {"low": 0.12, "mode": 0.2, "high": 0.28},
  "water_saturation": {"low": 0.2, "mode": 0.35, "high": 0.55},
  "recovery_factor": {"low": 0.2, "mode": 0.35, "high": 0.5},
  "net_to_gross": 0.8,
  "bo": 1.2,
  "risk": 0.6,
  "iterations": 5000,
  "seed": 42
}
```

STOIIP is `GRV * NTG * porosity * (1 - Sw) / Bo`. Recoverable volume multiplies
by `RF`. `risked_stoiip` multiplies every percentile by the risk probability.
Use `risks: {trap, reservoir, charge, seal}` for a component risk tree; the
probability is their product. Scalar values become zero-width triangular
distributions, so deterministic runs are exact.

For gas and gas-condensate set `fluid_type` to `gas` or `condensate`, `bg`
(reservoir m³ per surface m³, default 0.005) and `condensate_yield` (bbl per
MMSCF, default 30). GIIP is `GRV * NTG * porosity * (1 - Sw) / Bg`. Condensate
volume uses the gas volume in MMSCF; BOE adds gas BOE (5.8 Mcf per BOE) and
condensate barrels. `bo` applies only to oil.

Results store `stoiip` and `recoverable` for oil, or `giip`,
`recoverable_gas`, `condensate` and `boe` for gas, as P90/P50/P10/mean in m³ and
bbl.
`GET/DELETE /api/projects/{pid}/prospects[/{id}]` list and manage prospects.
The Seismic panel has a compact prospect form and result list.
