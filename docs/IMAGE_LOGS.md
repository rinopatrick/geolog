# Borehole images and manual dip picking

This increment stores a conditioned, unwrapped borehole image and lets an
interpreter fit dip picks. It does **not** perform vendor image conditioning,
automatic dip picking, aperture analysis or full coverage QC.

## Image assets

`POST /api/wells/{wid}/image-assets` uploads a PNG/JPEG/TIFF/BMP (≤50 MB) with:

- `depth_top`, `depth_bottom` (asset depth range)
- `azimuth_start`, `azimuth_end` (default 0–360)
- `borehole_radius` (required for trace-based dip fitting)
- `image_type`, `source`, optional `log_run_id`

Files are stored under `GEOLOG_ARTIFACT_DIR/images/<well_id>/<uuid>.<ext>`.
The response includes width/height (PNG) and a file endpoint:

```text
GET /api/wells/{wid}/image-assets/{id}/file
```

`POST /api/wells/{wid}/image-assets/import-dlis` extracts one 2D image channel
from a DLIS frame with `dlisio`, percentile-normalizes it and writes a grayscale
PNG. Vendor-specific conditioning remains out of scope.

## Manual dip picks

`POST /api/wells/{wid}/image-assets/{id}/dips` accepts either:

```json
{"trace": [[1000.3, 0], [1000.8, 90], [1000.1, 180], [1000.5, 270]]}
```

or direct values:

```json
{"depth": 1000.5, "dip_angle": 12.5, "dip_azimuth": 45}
```

Trace picks are fitted to `depth = z0 + a*cos(theta) + b*sin(theta)`.
`dip_angle = atan(amplitude / borehole_radius)`, and the maximum-depth azimuth
is the downdip direction. `r2` is stored and `quality` is `good` when
`r2 >= 0.8`, otherwise `review`.

Dip picks remain editable and are approved individually:

```text
GET    /api/wells/{wid}/image-assets/{id}/dips
POST   /api/wells/{wid}/image-assets/{id}/dips/{dip_id}/approve
DELETE /api/wells/{wid}/image-assets/{id}/dips/{dip_id}
```

## Limits

- The picker is API-first; a canvas UI is not included.
- No automatic sinusoid detection.
- No image orientation/acceleration/caliper correction.
- No fracture aperture or porosity from images.
- No committed third-party image-log fixture; DLIS extraction is exercised only
  through its error path in CI.
