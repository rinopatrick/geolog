# Structural framework

## Fault surfaces

`POST /api/seismic/{line_id}/fault-links/{link_id}/surface` grids the linked
fault points with inverse-distance weighting. Supply `velocity_model_id` to
store a depth surface; otherwise the grid is two-way time. `GET`/`DELETE`
endpoints are under `/api/seismic/{line_id}/fault-surfaces`.

## Horizon-based throw

`POST /api/seismic/{line_id}/fault-links/{link_id}/throw` samples a
depth-converted horizon on opposite sides of the fault trace and stores
`throw_source = horizon_offset`, median/mean/max throw in metres, and the
surface id in the link geometry. This is preferred over the cross-correlation
lag when a reliable horizon exists.

## Compartments

`POST /api/seismic/{line_id}/surfaces/{surface_id}/compartments` requires a
depth-converted surface with inline/crossline spacing. Cell area is
`inline_spacing_m * crossline_spacing_m` per grid node — the `inlines` and
`crosslines` arrays are trace labels (they may start at an arbitrary offset
or hold metre coordinates) and never scale the area. Pass `base_surface_id`
to use `min(base, contact) - top` for 3D compartment GRV. Each grid node is
assigned a side for every selected fault link by signed distance to the fault
polyline; the side bits form a compartment key. With a base surface, the
response also includes fault juxtaposition: top/base interval overlap sampled
on opposite sides of each fault trace (`reservoir_reservoir` vs `seal`). The endpoint aggregates:

- `cells`, `area_m2`, `grv_m3`, `mean_column_m` per compartment
- total GRV and cell area

The result is stored on the surface and returned in surface detail. The Seismic
panel exposes a contact input and a compartment list.

This is a map-based screening partition. It does not build a watertight 3D
framework, fault juxtaposition triangles, or throw-dependent relay zones.
