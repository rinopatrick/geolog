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
