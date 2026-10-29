# SEG-Y seismic

## Upload

`POST /api/projects/{pid}/seismic` accepts a SEG-Y file and stores it under
`GEOLOG_ARTIFACT_DIR/seismic`. The reader supports:

- IBM 4-byte float (SEG-Y format code 1)
- IEEE 4-byte float (format code 5)
- 2D lines and 3D lines with inline/crossline headers

The first 2,500 traces are indexed. The section endpoint decimates to at most
1,500 × 1,500 samples; the UI requests 600 × 600.

## View and picks

`GET /api/seismic/{line_id}/section` returns a decimated amplitude matrix plus
sample interval and original dimensions. The Seismic view renders it and lets
you click to build a horizon trace. `POST /api/seismic/{line_id}/horizons` stores
picks as `{trace, sample}` pairs in display coordinates.

## Limits

- No SEG-Y revision-2 extended headers, variable trace lengths, or compressed
  formats.
- Amplitudes are not gain-corrected, filtered, or interpreted.
- Horizon picks are manual; there is no auto-tracking or fault extraction.
- Large files are capped by `GEOLOG_MAX_UPLOAD_BYTES`; raise it for 3D volumes.
