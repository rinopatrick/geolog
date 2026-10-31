# Volve F-1 petrophysics fixture — provenance and licence

Subset (200 samples, 3400–3420 m MD) extracted from Equinor's Volve field
open dataset, well 15/9-F-1:

- `input.csv`: raw composite curves (`WLC_PETRO_COMPUTED_INPUT_1.LAS`)
- `reference_output.csv`: professional petrophysical interpretation
  (`WLC_PETRO_COMPUTED_OUTPUT_1.LAS`): PHIF, SW (Archie), VSH, KLOGH

Source: https://www.equinor.com/energy/volve-data-sharing
Licence: Equinor Open Data Licence (Volve terms and conditions):
https://www.equinor.com/content/dam/statoil/documents/what-we-do/Equinor-HRS-Terms-and-conditions-for-licence-to-data-Volve.pdf

Terms in short: download and use for research, study and development;
credit Equinor and the Volve licence partners with a link to the terms;
do not sell the material; do not present it in a misleading or distorted
manner. This fixture is a small adapted extract used for test calibration
only, with this notice preserved alongside it.

VSH in the reference output is (GR-15)/(135-15): a linear fit recovers
gr_clean=15, gr_shale=135 with R²=1. Note the Volve report headers cite
(GR-15)/235 — the delivered F-1 curves match /120, pinned by test so a
fixture swap cannot slip by unnoticed. KLOGH is log-derived
permeability, not core. This fixture validates consistency against a
professional interpretation, not against laboratory core measurements.
