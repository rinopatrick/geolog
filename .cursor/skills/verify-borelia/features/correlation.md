# Correlation (2-well tie)

## Sub-features

- Marker tie picks between well A and well B.
- Auto-correlate suggestion (`POST /api/correlation/auto-correlate`).
- Cross-section lines (`GET /api/correlation/cross-section`).

## How to get to it (user POV)

Correlation panel → select well pair → place manual ties or run AutoTie →
shift/stretch applied. `app.switchView('correlation')`.

## Driving it with HTTP

```bash
B=http://127.0.0.1:8137
curl -sf -X POST $B/api/correlation/auto-correlate -H 'Content-Type: application/json' \
  -d "{\"well_a_id\":$A,\"well_b_id\":$B2}" | tee artifacts/verify/<ts>/autocorr.json
```

Exact schema: `backend/routers/correlation.py`.

## Gotchas

- Needs TWO wells with overlapping curve families; seed data provides two demo wells.
- Shift/stretch persistence is per-profile; verify via re-GET, not just response.
