# SEG-Y seismic

## Upload

`POST /api/projects/{pid}/seismic` accepts a SEG-Y file and stores it under
`GEOLOG_ARTIFACT_DIR/seismic`. The reader supports:

- IBM 4-byte float (SEG-Y format code 1)
- IEEE 4-byte float (format code 5)
- 2D lines and 3D volumes with inline/crossline headers (bytes 189-196 read as
  signed int32, so negative or unassigned coordinates parse correctly)
- Only sample formats 1 (IBM float) and 5 (IEEE float) are supported; other
  SEG-Y formats are rejected at upload with a clear error

Upload writes a JSON index sidecar next to the SEG-Y file. The index scans every
trace header and stores byte offsets, sample counts, inlines and crosslines
without decoding the amplitudes. Trace start delays (header bytes 109-110,
signed) are indexed per trace and honored with datum correction in the seismic
tie time origin, so delayed traces align at true record time. Sections read
only the traces they need, so a 3D volume does not need to fit in memory.

The sequential section endpoint decimates the whole indexed line to at most
1,500 × 1,500 samples; the UI requests 600 × 600. It reports `line_trace_count`
and `sampled` so a large line can show its original size. The upload body is capped by
`GEOLOG_MAX_UPLOAD_BYTES` (default 512 MiB).

## 3D volume sections

`GET /api/seismic/{line_id}/volume` returns the sorted inline and crossline
values, counts, and `is_3d`. Volume index lists are capped at 5,000 values per
axis and set `truncated` when cut.

- `GET /api/seismic/{line_id}/inline/{value}/section`
- `GET /api/seismic/{line_id}/crossline/{value}/section`

Each section contains `labels` for the fast axis, `mode`, `value`, `label_name`,
and the same decimation metadata as the sequential section. Inline sections are
sorted by crossline; crossline sections are sorted by inline.

## View and picks

`GET /api/seismic/{line_id}/section` returns a decimated amplitude matrix plus
sample interval and original dimensions. The Seismic view renders it and lets
you click to build a horizon trace. `POST /api/seismic/{line_id}/horizons` stores
picks as `{trace, sample}` pairs in display coordinates.

Inline and crossline sections support the same picking workflow. A horizon now
stores `mode` (`line`, `inline`, `crossline`) and `section_value`, so picks made
on one inline section are not drawn on a different one. `auto-track` accepts the
same two fields and seeds from a horizon on the matching section.

## Auto-tracking

`POST /api/seismic/{line_id}/horizons/auto-track` tracks a reflection away from a
seed using normalized cross-correlation in a sample window. The seed can be an
existing horizon or explicit `{seed_trace, seed_sample}` display coordinates.
`window` controls the correlation window and `search_radius` the sample search
around the previous pick.

## Surface grids

`POST /api/seismic/{line_id}/surfaces` grids horizon picks into a time surface.
Use `horizon_ids` for an explicit set, `horizon_name` to group horizons with the
same name, or omit both to use every inline/crossline horizon. Only 3D
(`inline`/`crossline`) horizons are used; `line` picks are ignored.

The builder defaults to inverse-distance weighting. Pass `method: "kriging"` for
ordinary kriging with spherical/exponential/Gaussian variograms, `range`, `sill`,
`nugget`, `anisotropy_ratio` and `azimuth_deg`. The grid is capped at 96 × 96 by
default (`max_grid` up to 200); kriging uses up to 16 nearest neighbours. It returns
`inlines`, `crosslines`, `grid` (time in ms), `stats.point_count`,
`stats.coverage` and time min/max/mean. Surfaces are stored as
`SeismicSurface` rows. `GET .../surfaces/{id}/export.csv` writes
`inline,crossline,time_ms` for external tools.

The Seismic panel can build a surface by name, select a stored surface and draw
its time map. Fault traces are overlaid on the same inline/crossline map.

## Depth conversion

Project velocity models live under `/api/projects/{pid}/velocity-models`:

- `constant`: `{name, kind, velocity_m_s}`; depth = `velocity * twt_ms / 2000`.
- `layers`: `{name, kind, layers:[{top_ms, velocity_m_s}, ...]}`. The first layer
  must start at `top_ms: 0`; intervals are integrated cumulatively.

`POST /api/projects/{pid}/velocity-models/{id}/convert` converts a list of
`times_ms` for inspection. `POST /api/seismic/{line_id}/surfaces/{surface_id}/depth`
converts a stored surface with a model from the same project, stores
`depth_grid`, `depth_stats` and `velocity_model_id`, and makes the CSV export
include a `depth_m` column. The Seismic panel can add constant models, convert
the selected surface and toggle the map between time and depth.

`POST /api/projects/{pid}/velocity-models/invert-checkshot` inverts
interval velocities from checkshot `{depth, twt_ms}` pairs by piecewise
least squares (slope/segment × 2000 = m/s), with optional `holdout` points
reported as `holdout_rmse_m`. `save: true` stores the result as a `layers`
model. Synthetic two-layer recovery is exact (2000/3000 m/s within 5%,
residual < 1 m); field checkshots need monotonic, well-conditioned picks —
garbage picks fail loudly instead of producing a wild model.

## Well-to-seismic tie

`POST /api/wells/{wid}/seismic-ties` builds a synthetic trace from DT/RHOB,
extracts the seismic trace at `inline`/`crossline`, resamples the synthetic onto
the seismic time axis and searches a cross-correlation shift (`max_shift_ms`).
DT units `US/F` and `US/M` and depth units `FT`/`M` are normalized to SI before
TWT integration. SEG-Y trace delay (bytes 109–110) is indexed and added to the
tie time origin; `datum_ms` applies an additional project datum correction. Reflectivity is resampled to a uniform TWT grid before wavelet
convolution; the result is then mapped back to log depth. Checkshot coverage is
validated, and correlation excludes non-overlapping edges.

An optional `checkshot` list of `{depth, twt_ms}` replaces the DT-derived
time-depth mapping. The response stores the seismic/synthetic traces, `shift_ms`
and `correlation`; list/detail/delete endpoints are under
`/api/wells/{wid}/seismic-ties`. The Seismic panel can create a tie from the
current well and line and draw both traces.

## Fault detection

`POST /api/seismic/{line_id}/faults/detect` computes adjacent-trace coherence in
a 7-sample window, thresholds low-coherence pixels, filters low-energy areas and
groups vertical candidates into fault segments. Results are stored as
`SeismicFault` rows and returned for display.

## 3D fault linkage

`POST /api/seismic/{line_id}/faults/link-3d` detects faults on up to
`max_sections` inline sections, maps each pick to `{inline, crossline, sample}`,
and links segments between adjacent inlines when crossline and sample centres
stay within `crossline_tolerance` and `sample_tolerance`. A link needs at least
two inline sections. Results are stored as `SeismicFaultLink` rows and can be
read with `GET /api/seismic/{line_id}/fault-links` or deleted individually.

Each link also stores a geometry summary and a map polygon:

- `throw_ms`: median cross-correlation lag across the fault plane, in ms TWT.
- `vertical_extent_ms` and `throw_range_ms`: fault cut and per-section range.
- `dip_inline_ms_per_line`, `dip_crossline_ms_per_line` and `plane_rms_ms`:
  least-squares fault plane fit in time units.
- With `velocity_model_id`, geometry is also converted to depth: `domain` is
  `depth`, `throw_m`, `dip_inline_m_per_line`, `dip_crossline_m_per_line` and
  `plane_rms_m` are populated. `dip_angle_deg` is only calculated in the depth
  domain with inline/crossline spacing.
- `polygon`: convex hull of `{inline, crossline}` points, buffered for a
  collinear fault trace.

These are screening estimates from the seismic amplitudes. They do not include
velocity/depth conversion, fault throw from well correlations, or a structural
model.

## 1D wedge screening

`POST /api/seismic/wedge-model` is a stateless forward model: two
reflectors (top/base from AI contrast) convolved with a Ricker wavelet on a
uniform TWT grid, swept over bed thickness and frequency. Response includes
per-frequency tuning curves, `tuning_thickness_per_freq`, and a P10/P50/P90
band across the swept frequencies. The Seismic panel renders the curves, a
resolution table (empirical tuning vs analytic λ/4), and CSV download.

Honest limits, enforced by tests:

- 1D vertical incidence only. No AVO/offset, no diffraction, no Q
  attenuation, no multiples, no noise model.
- Narrowband verification recovers Widess λ/4 exactly; the broadband Ricker
  peak sits below λ/4 (pinned at 19 m for the 30 Hz reference case) — the
  kernel is tested for this, not forced onto the analytic value.
- `misfit_tie` scores synthetic-vs-observed correlation with lag scan.
  The Hawkins blind round-trip (extract wavelet → rebuild → correlate)
  reaches 0.93 vs 0.99 with the true wavelet. This is a synthetic recovery
  test on public LAS fixtures, **not** a field well tie.
- Polarity matters: opposite-sign top/base gives a tuning notch structure,
  not a peak — the model reports amplitudes, the interpreter decides.

## Limits

- No SEG-Y revision-2 extended headers, variable trace lengths, or compressed
  formats.
- Amplitudes are not gain-corrected, filtered, or interpreted.
- Fault linkage samples at most 64 inline sections per run and decimates each
  section to 600 × 600 for detection.
- Large files are capped by `GEOLOG_MAX_UPLOAD_BYTES`; raise it for 3D volumes.
