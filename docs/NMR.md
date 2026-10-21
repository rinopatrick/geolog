# NMR T2

GeoLog supports two NMR workflows:

1. **Vendor T2 bins** — interpret existing bin curves synchronously.
2. **Raw CPMG echoes** — regularized NNLS inversion as a background job.

The implementation is screening-grade. It does not model polarization, hydrogen
index, hydrocarbon correction or tool-specific processing.

## API

### Vendor bins

```http
POST /api/wells/{wid}/nmr/interpret
{
  "log_run_id": 12,
  "bin_mnemonics": ["T2B1", "T2B2", "T2B3"],
  "t2_bins_ms": [1, 10, 100],
  "cutoff_ms": 33,
  "include_curves": true,
  "save": true
}
```

Returns derived `NMRP`, `BVI`, `FFI`, `T2GM`, `KSDR`, `KCOATES` curves, depth,
stats and the semantics metadata. The inversion is saved unless `save=false`.

### Raw echoes

```http
POST /api/wells/{wid}/nmr/invert-async
{
  "log_run_id": 12,
  "echo_mnemonics": ["TE06", "TE12", "TE18"],
  "te_ms": [0.6, 1.2, 1.8],
  "n_bins": 24,
  "cutoff_ms": 33,
  "lambda": 0.1
}
```

Returns `202 {job_id}`. Poll `GET /api/jobs/{job_id}`. The job result contains
`inversion_id` and derived stats. Distribution:

```http
GET /api/wells/{wid}/nmr/inversions/{id}/distribution?max_points=800
```

## Math

For echoes `y`, kernel `K[i,j] = exp(-TE_i / T2_j)`, second-difference
regularizer `L` and non-negativity:

```
min ||Kx - y||² + λ²||Lx||²,  x >= 0
```

The default grid is 24 log-spaced bins from 0.3 to 3000 ms. λ is chosen once per
run (default 0.1). Vendor bins bypass inversion.

Derived curves:

- `NMRP = Σ x` — NMR porosity (fraction, assuming calibrated amplitudes)
- `BVI = Σ x(T2 < cutoff)`, `FFI = NMRP - BVI`
- `T2GM = exp(Σ x ln T2 / Σ x)`
- `KSDR = a · NMRP⁴ · T2GM²` (T2GM in ms; `a` configurable)
- `KCOATES = C · NMRP⁴ · (FFI/BVI)²` (`C` configurable)

Default cutoffs are 33 ms (sandstone); carbonate cutoffs are configurable.

## Storage

- `nmr_inversions`: method, bins, cutoff, λ, dimensions, input hash, engine version.
- `nmr_distributions`: float32 `(n_depth, n_bins)` amplitudes and float64 depth.

By default the derived scalars are upserted into `curve_data` so the viewer can
load `NMRP`, `BVI`, `FFI`, `T2GM`, `KSDR` and `KCOATES` after a refresh. Set
`save_curves=false` to return them only. The 2-D distribution is stored separately
and is never written into `curve_data`.
