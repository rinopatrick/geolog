# SEG-Y seismic

## Upload

`POST /api/projects/{pid}/seismic` accepts a SEG-Y file and stores it under
`GEOLOG_ARTIFACT_DIR/seismic`. The reader supports:

- IBM 4-byte float (SEG-Y format code 1)
- IEEE 4-byte float (format code 5)
- 2D lines and 3D volumes with inline/crossline headers

Upload writes a JSON index sidecar next to the SEG-Y file. The index scans every
trace header and stores byte offsets, sample counts, inlines and crosslines
without decoding the amplitudes. Sections read only the traces they need, so a
3D volume does not need to fit in memory.

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

The builder uses inverse-distance weighting on the picked inline/crossline
points and caps the grid at 96 × 96 by default (`max_grid` up to 200). It returns
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

## Well-to-seismic tie

`POST /api/wells/{wid}/seismic-ties` builds a synthetic trace from DT/RHOB,
extracts the seismic trace at `inline`/`crossline`, resamples the synthetic onto
the seismic time axis and searches a cross-correlation shift (`max_shift_ms`).

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

- `throw_ms`: median cross-correlation lag across the fault plane, in ms.
- `vertical_extent_ms` and `throw_range_ms`: fault cut and per-section range.
- `dip_inline_ms_per_line`, `dip_crossline_ms_per_line` and `plane_rms_ms`:
  least-squares fault plane fit in time units.
- `dip_angle_deg`: set when `inline_spacing_m` and `crossline_spacing_m` are
  supplied; this is a time-dip angle, not a depth-converted structural dip.
- `polygon`: convex hull of `{inline, crossline}` points, buffered for a
  collinear fault trace.

These are screening estimates from the seismic amplitudes. They do not include
velocity/depth conversion, fault throw from well correlations, or a structural
model.

## Limits

- No SEG-Y revision-2 extended headers, variable trace lengths, or compressed
  formats.
- Amplitudes are not gain-corrected, filtered, or interpreted.
- Fault linkage samples at most 64 inline sections per run and decimates each
  section to 600 × 600 for detection.
- Large files are capped by `GEOLOG_MAX_UPLOAD_BYTES`; raise it for 3D volumes.
