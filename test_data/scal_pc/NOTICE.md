# SCAL Pc fixtures — provenance and licence

Sw–Pc pairs extracted from the U.S. DOE Pc-to-RP dataset (Moodie / NETL,
Southwest Regional Partnership):

- Source workbook: `pc-to-rp-two-phase-data_rev3.xlsm`, sheet
  `RelPermPcChartData-raw`, DOI 10.18141/1998892
  (https://doi.org/10.18141/1998892,
  https://edx.netl.doe.gov/dataset/pc-to-rp-two-phase-method)
- Licence: GNU Free Documentation License (per the EDX dataset page).
  This notice travels with the derived CSVs.
- Files here:
  - `berea_sandstone_sw_pc.csv` (46 pts, Berea SS, MICP poro 22.1%,
    perm 914 mD, Krevor 2011/2012)
  - `viking_sandstone_sw_pc.csv` (82 pts, Viking SS)
  - `tuscaloosa_sandstone_sw_pc.csv` (52 pts, Tuscaloosa SS)

What the tests pin (see `tests/test_sat_height_scal.py`):

- Berea and Viking fit Brooks-Corey with R² ≥ 0.8 — the model works on
  textbook drainage curves.
- Tuscaloosa is bimodal (sharp entry plus a Pc=0 tail from mixed rel-perm
  rows): Brooks-Corey must score R² < 0.5 there. The model demonstrably
  knows when it does not apply — enforced by test, not by comment.
