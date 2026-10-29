# Petrophysics uncertainty

`POST /api/wells/{wid}/petro-uncertainty` runs a per-depth Monte Carlo over
Archie, Simandoux or Indonesian saturation:

- samples `a`, `m`, `n`, `Rw`, Vsh scale and PHIE scale by `variation_pct`
- returns P90/P50/P10 bands for Sw, PHIE and Vsh at each depth
- optional `start_depth` / `stop_depth`, `iterations` up to 500, `seed`
- caps the depth samples at 3,000 and the response at 1,500 points

The Sensitivity view has a **Curve uncertainty** action that draws the three
bands. The existing **Run Sensitivity** action remains the net-pay Monte Carlo
with driver ranking. The deterministic multimineral solver remains available
from the Petrophysics toolbar.
