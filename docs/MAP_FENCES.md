# Map and fence workspace

## Project map

`GET /api/projects/{pid}/map` returns:

- wells with latitude/longitude
- seismic lines and their inline/crossline bounds
- well-to-seismic ties as inline/crossline points
- fault links with points/polygons
- surface centroids and depth stats
- prospects with their stored volume results

The Map view has two modes. **Wells** plots latitude/longitude and selects a
well on click. **Seismic** plots inline/crossline, fault polygons, surface
centroids, prospects and tie points.

## Arbitrary lines

`GET /api/seismic/{line_id}/arbitrary-line` samples the nearest traces between
two inline/crossline points and returns a decimated section. If inline/crossline
spacing is supplied, axis labels are distances in metres; otherwise they are
trace indices.

## Fences

`POST /api/seismic/{line_id}/fences` accepts up to six segments and returns one
section per segment. The Seismic panel's **Add fence** appends arbitrary-line
sections to a fence canvas; **Clear** removes them.

Both endpoints are readers. They do not interpolate amplitudes or perform
pre-stack imaging; they select the nearest existing traces.
