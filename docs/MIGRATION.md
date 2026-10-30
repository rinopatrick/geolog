# 3D depth migration

`POST /api/seismic/{line_id}/migrate-3d` runs a **post-stack constant-velocity
3D Kirchhoff depth migration** on a decimated SEG-Y cube.

## Inputs

- `velocity_m_s` (500–8000)
- `inline_spacing_m`, `crossline_spacing_m`
- `max_inlines` / `max_crosslines` (2–32)
- `max_samples` (8–256)
- `max_depth_samples` (8–192)
- optional `aperture_m`

The cube is built by binning traces to a regular inline/crossline grid and
averaging duplicates. Missing bins are zero.

## Algorithm

For each output point `(x, y, z)`, traces are summed along the constant-velocity
travel-time surface:

```
r = sqrt((x-x')^2 + (y-y')^2 + z^2)
t = 2r / v
weight = z / r
```

The output is a depth cube stored as a compressed NPZ artifact. Endpoints list
migrations, return metadata, extract inline/crossline depth sections and delete
the artifact.

## Limits

This is post-stack, isotropic, constant-velocity Kirchhoff migration. It is not
pre-stack, VTI/TTI anisotropic, RTM, or a velocity-model-building workflow. The
grid is capped at 32×32 lateral and 192 depth samples; larger volumes need an
external migration engine. The result is a screening depth image, not a
certified migrated volume.

Amplitudes are fold-normalized **per voxel**: each output point is divided by
the sum of obliquity weights that actually contributed to it. Traces outside
`aperture_m` (and dead/NaN traces) contribute zero weight and zero fold, so
narrowing the aperture does not dilute the image toward zero. This preserves
relative amplitude balance for screening, but there is no spherical-spreading
(`1/r`) correction, no anti-alias filter, and no wavelet shaping — do not use
the amplitudes for AVO or quantitative inversion.
