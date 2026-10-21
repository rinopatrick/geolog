# GeoLog #9 — NMR T2 inversion
**Recommendation:** use regularized non-negative least squares (NNLS) on raw CPMG echoes, with SciPy, and bypass inversion when the LAS already carries vendor T2 bin curves.
- Solve `min ||Kx−y||² + λ²||Lx||², x≥0`, where `K[i,j]=exp(−TE_i/T2_j)` and `L` is a second-difference operator. Stack `[K; λL]` and call `scipy.optimize.nnls` [3][6].
- Default grid: 24 log-spaced bins over 0.3–3000 ms, trimmed to the acquisition window. Use 16 bins only if storage is critical.
- Choose one λ per log run on a 500-depth subset (L-curve slope or fixed SNR default), then apply it to all depths. Do not run an L-curve per depth; that multiplies runtime by the number of λ trials [7][13].
- Run raw-echo inversion as an async job. Vendor-bin interpretation can stay synchronous.
**Why SciPy:** `scipy.optimize.nnls` is an active-set non-negative solver with a `maxiter` argument [3]. Pin `scipy==1.15.3`: it supports Python ≥3.10 and NumPy ≥1.23.5,<2.5, so it fits NumPy 1.26.4 and the advertised 3.10+ floor [4]. SciPy 1.17.0 also fits NumPy 1.26.4 but requires Python ≥3.11 [5]; Docker and CI are already 3.11, so 1.17 is the choice only if 3.10 support is dropped. cp310 wheels exist for 1.15.3.
**Alternatives**
| Option | Verdict |
|---|---|
| Vendor fixed bins | Use when present. No raw echoes needed; log displays already inverted bins such as 4–512 ms [11][12]. Sparse: the 33 ms cutoff falls between the 32 and 64 ms bins (inference), and T2gm/cutoff volumes are quantization-limited. |
| Fixed-bin fitting from raw echoes | This is NNLS on a fixed grid; not a separate method. Choose grid density, not “bins vs NNLS.” |
| Unregularized NNLS | Reject as default: ill-posed and spiky at realistic SNR [6]. Keep only as a diagnostic. |
| BRD/UPEN/CONTIN | Same non-negative, smoothed-inversion family; more automatic smoothing machinery than the MVP needs [6]. Defer. |
| Pure-NumPy Lawson–Hanson | Fallback only if a dependency freeze blocks SciPy. It matched SciPy to 3e-17 in a local check but ran 8–28× slower. |
**Performance (local, single core, SciPy 1.17.0/NumPy 2.4.1, AMD64):** 128 echoes × 24 bins = 0.13 ms/depth (1.3 s per 10k, 13 s per 100k); 256×32 = 0.27 ms (2.7/27 s); 600×48 = 0.79 ms (7.9/79 s). The pinned 1.26.4 stack should be the same order; verify in CI. Chunk depth (2k–5k) and load one echo matrix at a time: 100k × 512 echoes is ~410 MB in float64.
**Data model**
```sql
nmr_inversions(id PK, log_run_id FK, method, t2_bins_ms JSON,
  lambda, cutoff_ms, params_hash, engine_version, created_at)
nmr_distributions(inversion_id FK PK, n_depth, n_bins, amplitudes BLOB)
```
Store amplitudes as C-order float32 `(n_depth, n_bins)`, one BLOB per inversion, not one SQLite row per depth. At 24 bins that is 96 B/depth, 9.6 MB per 100k; 16 bins is 6.4 MB. Derived scalars stay ordinary `CurveData` float64 rows: `NMRP`, `T2GM`, `BVI`, `FFI`, `KSDR`, `KCOATES`. Do not put the 2-D float32 array into `CurveData.data_binary`: existing readers assume 1-D float64 [15]. Store bin edges and `params_hash` so cutoffs can be recomputed without re-inversion, and a changed λ creates a new inversion rather than overwriting history. Add the tables through Alembic, per #7 [2].
**API shape**
```text
POST /api/wells/{wid}/nmr/interpret          # sync, vendor bins -> derived curves
POST /api/wells/{wid}/nmr/invert-async       # 202 {job_id}, raw echoes
GET  /api/wells/{wid}/nmr/inversions/{iid}/distribution?max_points=800
GET  /api/jobs/{job_id}
```
Body: `{log_run_id, echo_mnemonics, te_ms, t2_bins_ms:{min,max,count}, regularization:{order:2,lambda:"auto"}, cutoff_ms:33}`. Require `require_interpreter`, matching other compute endpoints [16]. Reuse the existing job registry and `/api/jobs/{job_id}` polling [17]. Downsample distributions to 800 depth points, matching the existing curve downsampling convention [16].
**Formulas:** `NMRP = Σ amplitudes` in fraction units; `BVI = Σ amplitudes(T2 < cutoff)`, `FFI = NMRP − BVI`; `T2GM = exp(Σ a_i ln T2_i / Σ a_i)` [8]. `KSDR = a φ⁴ T2GM²`, with `a` calibrated and a literature default near 4 for sandstone [9][10]. `KCOATES = [(φ/C)²(FFI/BVI)]²`, equivalently `10⁴ φ⁴(FFI/BVI)²` for fraction porosity with C≈0.1 [8]. Cutoffs: 33 ms sandstone, ~90–92 ms carbonate [8][11]. Expose `a`, `C`, and cutoff as parameters; do not reuse the existing Swir-based Coates endpoint [16].
**Synthetic tests**
1. Forward-model known unimodal and bimodal log-normal distributions; add Gaussian noise; assert porosity within 1% relative, T2GM within 5%, peak within one bin at SNR ≥50.
2. Mono-exponential: one peak, no negative amplitudes, no spurious peaks above 5% of maximum.
3. Bimodal 10/100 ms: resolved at SNR 100; document failure at SNR 20.
4. λ sweep: residual decreases and roughness increases monotonically; λ=0 produces spikes; selected λ is stable across depth subsets.
5. Cutoff volumes: analytic BVI/FFI, cutoff on a bin edge, cutoff outside the grid.
6. Robustness: zero/negative/NaN echoes, truncated train, constant signal, all-zero distribution.
7. Golden-array regression with fixed fixtures and tolerances; same input must produce identical output.
8. Performance smoke test on 10k depths, non-blocking/nightly.
**Risks**
- λ and the SDR/Coates constants are not calibrated against core; bundled LAS files contain no raw NMR echoes, so validation is synthetic-only until a real echo train is supplied.
- Short wait time, hydrogen-index and hydrocarbon effects bias porosity and cutoff volumes; this scope assumes water-filled pores and no polarization correction.
- 100k-depth inversion occupies a shared worker for tens of seconds; use chunked progress and avoid the 4-worker pool starvation.
- SciPy adds a large wheel and pins the project to Python 3.10–3.12 while NumPy 1.26.4 is fixed.
- Vendor bins are already inverted and cannot be re-sharpened; storing them alongside a raw-echo inversion risks two conflicting “truths.”
**Coverage status:** Read issue #9 and #7, repository models/routers/jobs, SciPy/PyPI metadata, and cited literature abstracts/docs. Benchmark is local and not on the pinned NumPy version. Did not validate against real NMR logs; none are bundled. No files edited.
### Evidence table
| # | Source | URL | Key claim | Type | Confidence |
|---|--------|-----|-----------|------|------------|
| 1 | GeoLog issue #9 | https://github.com/rinopatrick/geolog/issues/9 | Scope: compare inversion, bins, storage, API, tests | primary | high |
| 2 | GeoLog issue #7 | https://github.com/rinopatrick/geolog/issues/7 | Alembic, minimal change, additive API | primary | high |
| 3 | SciPy `nnls` docs | https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.nnls.html | Active-set NNLS, `maxiter`, non-negative solution | primary | high |
| 4 | SciPy 1.15.3 PyPI | https://pypi.org/project/scipy/1.15.3/ | Python ≥3.10; NumPy ≥1.23.5,<2.5; cp310 wheels | primary | high |
| 5 | SciPy 1.17.0 PyPI | https://pypi.org/project/scipy/1.17.0/ | Python ≥3.11; NumPy ≥1.26.4,<2.7 | primary | high |
| 6 | Buttler, Reeds & Dawson 1981 | https://doi.org/10.1137/0718025 | Non-negative first-kind inversion with optimal smoothing | primary | high |
| 7 | Hansen 1992 L-curve | https://doi.org/10.1137/1034115 | L-curve for Tikhonov parameter selection | primary | high |
| 8 | Coates et al., NMR Logging Principles | https://vista-clara.com/wp-content/uploads/2020/10/NMRLoggingPrinciples-10.1.1.206.319.pdf | Area=porosity; Coates/SDR; 33/92 ms cutoffs; BVI/FFI | primary book | medium |
| 9 | Kenyon et al. 1988 | https://doi.org/10.2118/15643-pa | Origin of NMR permeability correlations | primary | high |
| 10 | SPWLA cuttings paper | https://www.kmstechnologies.com/Files/SPWLA_2004_final.pdf | SDR `PERM=a·T2gm²·POR⁴`; a≈4 sandstone | conference | medium |
| 11 | Oil & Gas Journal | https://www.ogj.com/home/article/17215807/nmr-tools-afford-new-logging-choices | Vendor bins 4–512 ms; 33/90 ms cutoffs | trade | medium |
| 12 | Geomage g-Space manual | https://doc.geomage.com/g-Space/nmr-t2-interpretation.html | Interpretation consumes already-inverted arrays | vendor doc | medium |
| 13 | 2016 regularization study | https://doi.org/10.1007/s12182-016-0093-6 | Compares DP/GCV/L-curve; slope-of-L-curve efficient | primary | high |
| 14 | NumPy 1.26.4 PyPI | https://pypi.org/project/numpy/1.26.4/ | CPython 3.9–3.12 wheels | primary | high |
| 15 | GeoLog `models.py` | https://github.com/rinopatrick/geolog/blob/main/backend/models.py | `CurveData` stores 1-D float64 binary blobs | primary | high |
| 16 | GeoLog `wells.py` | https://github.com/rinopatrick/geolog/blob/main/backend/routers/wells.py | Existing curve/summary endpoints; Swir-based Coates | primary | high |
| 17 | GeoLog `jobs.py` | https://github.com/rinopatrick/geolog/blob/main/backend/jobs.py | Background job registry and status | primary | high |
