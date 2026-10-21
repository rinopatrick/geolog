# Model Prerequisites
- compute-sw: requires RT + porosity curve family
- multimineral: best with RHOB + NPHI + DT + GR
- permeability-multi: requires porosity + saturation
- dual-water: requires RT + Vcl/Qv proxies
- electrofacies: requires at least 3 curves and enough valid samples
- DLIS/LIS: `dlisio==1.0.4` (installed from `backend/requirements.txt` on Python >= 3.10). Without it, uploads fall back to a heuristic scan that returns `CURVE1`/`CURVE2` and a warning.
