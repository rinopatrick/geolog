# Petrophysics uncertainty

`POST /api/wells/{wid}/petro-uncertainty` runs a per-depth Monte Carlo over
Archie, Simandoux or Indonesian saturation. When RHOB is present it uses a
density-neutron effective porosity (`phi_D` from RHOB, gas-crossover heuristic,
average with NPHI); otherwise it falls back to NPHI. `rho_ma`, `rho_f` and
`phi_sh` are configurable.

- samples `a`, `m`, `n`, `Rw`, `Rsh`, Vsh scale and PHIE scale by `variation_pct`
- returns P90/P50/P10 bands for Sw, PHIE and Vsh at each depth
- optional `start_depth` / `stop_depth`, `iterations` up to 500, `seed`
- caps the depth samples at 3,000 and the response at 1,500 points

Saturation equations are shared with the deterministic petrophysics endpoint:

- Archie: `Sw^n = aRw / (phi^m Rt)`
- Simandoux: `Sw^n = (aRw/phi^m)(1/Rt - Vsh/Rsh)`
- Indonesian: `Sw = [1/(sqrt(Rt)(sqrt(phi^m/(aRw)) + sqrt(Vsh/Rsh)))]^(2/n)`

`Rsh` defaults to 4 ohm·m and is exposed in the Petrophysics and Sensitivity
forms. The Sensitivity view has a **Curve uncertainty** action that draws the
three bands. The existing **Run Sensitivity** action remains the net-pay Monte
Carlo with driver ranking. The deterministic multimineral solver remains
available from the Petrophysics toolbar.

## Shmin sanity anchor (NPD LOT)

Casing-shoe LOT mud equivalents from the NPD FactMaps
`wellbore_casing_and_lot` layer (`test_data/npd_lot/`, NLOD 2.0)
convert to a Shmin-gradient band via `lot_gradient_band` (emw × 0.4335).
On the 500-record subset the median sits near the default
`shmin_gradient` assumption — an anchor, not a calibration: shoe tests
are shallow and do not replace a well-specific LOT/XLOT/DFIT at
reservoir depth.

## Calibration against reference interpretation

`POST /api/wells/{wid}/petro-calibration` fits GR endpoints and shale
porosity against reference curves: body `{gr, vsh_ref, phi_raw, phi_ref,
save}` where `phi_raw` is the interpreter's density-neutron blend before
shale correction. Returns fitted `{gr_clean, gr_shale, phi_sh}` with MAE.
With `save: true` the params persist to `PetroParams`.

Reference: Volve F-1 professional interpretation subset
(`test_data/volve_f1/`, see `NOTICE.md` for Equinor licence terms).
On that fixture, calibration cuts VSH MAE 0.25 → 0.07 and PHIE MAE
0.063 → 0.006 vs the min-max/0.3 defaults. KLOGH is log-derived,
not core — this validates consistency with a professional interpretation,
not with laboratory measurements.

## Plug transform check

`POST /api/wells/{wid}/plug-transform-check` is the stateless complement
to the DB-backed `core-calibration` endpoint: it fits a log-linear
porosity-permeability transform on a plug table alone (no log run
needed). Body: `{plugs: [{porosity_pct, perm_klinkenberg_md, sw_pct,
...}]}`. Returns slope/intercept/R²/residual spread plus the laboratory
Sw baseline. On the RealPore NCS fixture (300 plugs, well 35/11-7):
R² 0.53, residual σ 0.10 log10, median Sw 57.7%.

Reference: RealPore NCS subset (`test_data/realpore_ncs/`, CC-BY 4.0,
attribution to GeoProvider — see `NOTICE.md`). Routine plugs only:
porosity, Klinkenberg permeability, fluid saturations. No Pc curves,
no SCAL — this validates transforms against laboratory plugs, not
capillary-pressure behaviour.

## Deterministic solver validation

The VCL/PHIE kernels live in `backend/petro_deterministic.py` and are
shared by the `compute_saturation` endpoint (same code path, not a copy).
Validated against the Volve F-1 fixture:

- IGR with gr_clean=15/gr_shale=135 reproduces reference VSH (MAE < 1e-3,
  CSV rounding floor). Report headers cite /235, delivered curves use /120.
- Density-neutron blend tracks reference PHIF (mean resid < 0.02, max < 0.08).
- Archie Sw rank-tracks the reference (Spearman > 0.7 at Rw=0.02). Absolute
  Sw needs the interpreter's Rw (not in delivered curves); Rw=0.1 default
  saturates this interval to 1.0 — documented, not hidden.

## Saturation-height vs measured Pc

`fit_model` is checked against DOE Pc-to-RP Sw–Pc pairs
(`test_data/scal_pc/`, GFDL — see `NOTICE.md`): Berea and Viking
sandstones fit Brooks-Corey with R² ≥ 0.8, while bimodal Tuscaloosa
scores R² < 0.5 by test. When neither clean curve fits, the saturation-height
models must be treated as screening, not calibrated.

## Plug transform check

`POST /api/wells/{wid}/plug-transform-check` is the stateless complement
to the DB-backed `core-calibration` endpoint: it fits a log-linear
porosity-permeability transform on a plug table alone (no log run
needed). Body: `{plugs: [{porosity_pct, perm_klinkenberg_md, sw_pct,
...}]}`. Returns slope/intercept/R²/residual spread plus the laboratory
Sw baseline. On the RealPore NCS fixture (300 plugs, well 35/11-7):
R² 0.53, residual σ 0.10 log10, median Sw 57.7%.

Reference: RealPore NCS subset (`test_data/realpore_ncs/`, CC-BY 4.0,
attribution to GeoProvider — see `NOTICE.md`). Routine plugs only:
porosity, Klinkenberg permeability, fluid saturations. No Pc curves,
no SCAL — this validates transforms against laboratory plugs, not
capillary-pressure behaviour.
