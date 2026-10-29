# Source-rock screening

`POST /api/wells/{wid}/source-rock` computes TOC and kerogen bulk volume from a
log run and stores `TOC` and `VKER` curves on that run.

## Methods

- **Passey ΔlogR (sonic):** `ΔlogR = log10(Rt/Rt_base) + 0.02*(DT - DT_base)`
- **Passey ΔlogR (density):** `ΔlogR = log10(Rt/Rt_base) - 2.5*(RHOB - RHOB_base)`
- **Schmoker:** `TOC = 154.497/RHOB - 57.261`

Passey TOC: `TOC = ΔlogR * 10^(2.297 - 0.1688*LOM) + TOC_base`, clamped to
0–60 wt%. Without explicit baselines, the API uses the 20th percentile of Rt
and the 80th percentile of the porosity curve (shale-side baseline).

Kerogen volume: `VKER = (TOC/100) * RHOB / 1.2`, clamped to 0–1 v/v. If RHOB is
missing, the API assumes 2.5 g/cc and returns a warning.

## Limits

- Passey is a screening method; pick a real shale baseline for quantitative work.
- LOM must come from maturity data.
- TOC is reported in weight percent, not volume percent.
- No correction for kerogen density variation or mineral matrix effects.
