# GeoLog #14 — Geomechanics MVP
**Recommendation.** Ship a deterministic, calibration-gated screening MVP. Compute overburden stress, pore pressure (Eaton default; Bowers optional), dynamic elastic moduli, and a vertical-well Kirsch/Mohr-Coulomb mud window from existing DT/DTS/RHOB/GR/DEPT. Emit SHmax, static moduli, sanding and fracture-slip results only when their calibration inputs exist; otherwise return a labelled scenario, never a bare number. This fits GeoLog’s curve/report architecture and avoids presenting unvalidated geomechanics as design output. Issue: https://github.com/rinopatrick/geolog/issues/14
## Scope
- New pure module `backend/geomechanics.py` plus router `/api/wells/{wid}/geomechanics`.
- Read curves with the existing `CurveData` binary pattern; reuse `DeviationSurvey`, `RFTPoint`, `DSTTest`, `core-calibration`.
- Curves: `SIGV`, `PP_EATON`, `PP_BOWERS`, `SIG_HMIN`, `SIG_HMAX`, `E_DYN`, `NU_DYN`, `E_STA`, `UCS`, `MW_MIN`, `MW_MAX`, `BO_WIDTH`, `SAND_CDP`, `FRAC_SLIP`.
- Calibration: fit Eaton exponent/NCT and Bowers A, B, U to RFT/MDT/DST; fit `E_static = a + b·E_dynamic` to core; accept UCS, friction angle, Shmin/LOT/DFIT as parameters.
- v1 limited to vertical or near-vertical wells (inc ≤ 30°); flag others.
**Non-goals:** 3D/FE modelling, anisotropy, deviated-well stress transformation, sand-rate prediction, fracture propagation, depletion/time-lapse, automatic image-log picking, DIF interpretation, thermal/chemical effects, probabilistic inversion.
## Formulas and inputs
| Output | Formula | Inputs / guard |
|---|---|---|
| Overburden | `Sv = ∫ρ(z)g dz` | RHOB; water column and shallow fill; report integration gaps |
| Effective stress | `σ' = S − αPp` | α default 1; configurable Biot |
| Eaton | `Pp = Sv − (Sv − Pn)(DTn/DT)^n` | DT, shale flag, NCT; `n=3` sonic default [1][12] |
| Bowers | `V = Vw + Aσ'^B`; `Pp = Sv − ((V−Vw)/A)^(1/B)` | DT, density, calibration pairs; unloading variant needs `σ'max`, `U` [2] |
| Elastic | `Vp=304800/DT`, `Vs=304800/DTS`; `G=ρVs²`; `K=ρ(Vp²−4/3Vs²)`; `ν=(Vp²−2Vs²)/(2(Vp²−Vs²))`; `E=2G(1+ν)` | DT, DTS, RHOB; reject Vs≥Vp, ν∉[0,0.5] [8] |
| Missing DTS | `Vs=(Vp−1.36)/1.16` km/s | only clastic, water-saturated; mark estimated [6] |
| SHmax from breakout | `σH=[UCS+Pw+αPp+σh(2cosW−1)]/(1+2cosW)` | full breakout width W, radians; Kirsch at θ=90°±W/2; W<90° [3][5] |
| Wellbore | `σθθ=3σH−σh−Pw−αPp`; `Pw_min=3σH−σh−αPp−UCS`; `Pw_max=Shmin` | vertical well; apply mud margins [3][5] |
| Sand screening | `Pwf_crit=3σH−σh−αPp−UCS`; `CDP=Pp−Pwf_crit` | openhole only; no perforation/rate claim [9] |
| Fracture slip | `τ ≥ μ(σn−Pp)+c`; opening if `Pp ≥ σn` | requires plane dip/azimuth, μ, c [3] |
Dynamic-to-static transforms are not universal; push them behind a calibration gate and label published correlations unverified [7][8].
## Minimal API
`POST /api/wells/{wid}/geomechanics/compute` with `{models, params, calibration}` returns `{curves, summary, warnings, provenance}`. `GET /api/wells/{wid}/geomechanics/report?format=json|csv|pdf` uses the same computation. Stateless v1: no migration; calibration arrays are supplied per request and recorded by existing audit. Every output carries `source: measured|calibrated|correlation|assumed` and a confidence tag.
## Tests
- Golden one-point values for Eaton, Bowers, elastic moduli, breakout inversion, collapse pressure.
- Invariants: Sv monotonic with density; `Pn ≤ Pp ≤ Sv`; `0<ν<0.5`; wider breakout with higher SHmax; higher UCS lowers sanding risk.
- Edge cases: missing RHOB/DT → 400; DTS absent → Castagna with warning; NaN gaps preserved; FT/M conversion; calibration <3 points → 400; inc >30° warning.
- Update route-inventory and report-contract tests; assert every curve has provenance.
## Calibration, uncertainty, limits
Required: RFT/MDT/DST for Pp; LOT/XLOT/DFIT for Shmin [4][11]; core triaxial for UCS, φ and static moduli; oriented caliper/image log for orientation [5]; fracture mapping; sand tests/production observations [9].
Uncertainty: report sensitivity bands for Eaton n/NCT, α, UCS, μ and Shmin. Do not invent P10/P50/P90 without distributions. Absolute SHmax is the weakest output because it inherits UCS error [3][5].
Cannot be validated without lab/core: static transform coefficients, UCS/φ, Biot coefficient, tensile strength, sand onset/rate, fracture cohesion/friction, anisotropy, and absolute SHmax. Tests can prove arithmetic and physical bounds, not field validity. Pore-pressure mechanism choice also needs measured pressures.
**Risks:** false confidence from uncalibrated transforms; CALI alone cannot give orientation; density gaps corrupt Sv; Eaton/Bowers mechanism mismatch; sand and fracture screens are misleading outside their assumptions. Mitigate with hard calibration gates, warnings, and “screening only” report language.
## Sources
1. Eaton, *The Equation for Geopressure Prediction from Well Logs* — https://doi.org/10.2118/5544-MS
2. Bowers, *Pore Pressure Estimation From Velocity Data* — https://doi.org/10.2118/27488-PA
3. Zoback et al., *Determination of stress orientation and magnitude in deep wells* — https://doi.org/10.1016/j.ijrmms.2003.07.001
4. Zoback et al. PDF — https://pangea.stanford.edu/departments/geophysics/dropbox/STRESS/publications/MDZ%20PDF's/2003/Zoback%20et%20al.%20Final_ISRM.pdf
5. BGS, *Characterising the UK stress field* — https://earthwise.bgs.ac.uk/index.php/OR/17/048_Characterising_the_UK_stress_field_and-in-situ_stresses
6. USGS SIR 2013-5141, shear-wave prediction — https://pubs.usgs.gov/sir/2013/5141/pdf/SIR13-5141.pdf
7. *Development of a new correlation to determine the static Young’s modulus* — https://link.springer.com/article/10.1007/s13202-017-0316-4
8. Stanford, *Static and Dynamic Moduli* — https://pangea.stanford.edu/~jack/StatDynModuli.pdf
9. CSIRO, *Sand production prediction* — https://research.csiro.au/oilandgas/wp-content/uploads/sites/49/2015/10/Sand-production-prediction-2015.pdf
10. SPE, *Methods to determine pore pressure* — https://onepetro.org/spe/general-information/1803/Methods-to-determine-pore-pressure
11. DFIT closure-stress review — https://www.sciencedirect.com/science/article/pii/S0920410518307010
12. Sarker & Batzle, Eaton exponent — https://sites.mines.edu/crusher/wp-content/uploads/sites/126/2018/03/Publication_Sarker_Batzle_tle200806_effective_stress_coefficient_shales.pdf
Skipped: no code changes or repo edits (read-only task); no reproduction of published transforms. Risk: source PDFs behind 403/paywalls were read via search excerpts, so exact equation constants should be rechecked before implementation.
