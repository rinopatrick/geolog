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
