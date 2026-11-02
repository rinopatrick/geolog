# Petrophysics quicklook

## Sub-features

- Archie water saturation (`POST /api/wells/{wid}/compute-sw`).
- VCL models Larionov/Clavier/Steiber (`POST /api/wells/{wid}/vcl-models`).
- Dual-water, lithology, permeability endpoints (same shape).

## How to get to it (user POV)

Petrophysics panel → select well + parameters (a, m, n, Rw) → run → Sw returned
as JSON (stateless: NOT stored as a curve) and plotted. `app.switchView('petrophysics')`.

## Driving it with HTTP

```bash
B=http://127.0.0.1:8137
H='-H "X-User-Role: admin"'
# model defaults to archie; also: simandoux, indonesian, waxman_smits, dual_water.
# All params optional (a=1, m=2, n=2, rw=0.1, vsh_method=larionov_tertiary, ...).
curl -sf -X POST $B/api/wells/$WID/compute-sw -H 'Content-Type: application/json' $H \
  -d '{"model":"archie","a":1,"m":2,"n":2,"rw":0.05}' | tee artifacts/verify/<ts>/sw.json
# proof: response 200 + depth array matches log run + sane stats
curl -sf -X POST $B/api/wells/$WID/compute-sw -H 'Content-Type: application/json' $H \
  -d '{"model":"archie","a":1,"m":2,"n":2,"rw":0.05}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['depth']), 'pts, sw_mean', d['stats']['sw_mean'])"
```

Exact request schema: `backend/routers/wells_compute.py` (`compute-sw`, `vcl-models`).

## Gotchas

- Requires resistivity + porosity curves on the well; upload KGS sample first.
- Well must have a log run or compute returns 404 "No log run".
- Hingle/probability/moveable panels auto-POST on `switchView` and return 404
  "Required curves not found" when the well lacks that panel's default curves
  (e.g. hingle defaults `rt_curve=RT`, KGS sample has RILD/RILM instead — pick
  the existing curve in the panel dropdown). This is missing-prerequisite data,
  not a bug; the full-panel smoke (`e2e_panel_smoke.js`) only passes green on a
  DB whose wells carry the needed curves.
