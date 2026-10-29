# Structural framework

## Fault surfaces

`POST /api/seismic/{line_id}/fault-links/{link_id}/surface` grids the linked
fault points with inverse-distance weighting. Supply `velocity_model_id` to
store a depth surface; otherwise the grid is two-way time. `GET`/`DELETE`
endpoints are under `/api/seismic/{line_id}/fault-surfaces`.

## Compartments

`POST /api/seismic/{line_id}/surfaces/{surface_id}/compartments` requires a
depth-converted surface with inline/crossline spacing. Each grid node is assigned
a side for every selected fault link by signed distance to the fault polyline;
the side bits form a compartment key. The endpoint aggregates:

- `cells`, `area_m2`, `grv_m3`, `mean_column_m` per compartment
- total GRV and cell area

The result is stored on the surface and returned in surface detail. The Seismic
panel exposes a contact input and a compartment list.

This is a map-based screening partition. It does not build a watertight 3D
framework, fault juxtaposition triangles, or throw-dependent relay zones.
