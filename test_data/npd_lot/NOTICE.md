# NPD LOT fixture — provenance and licence

Subset (500 LOT records, ordered by OBJECTID) from the Norwegian Offshore
Directorate (Sokkeldirektoratet) FactMaps `wellbore_casing_and_lot` layer:

- Source API: https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer/5001/query
  (filter `wlbLotMudDencity>0`, fields: wellbore, casing/hole depth,
  LOT/FIT mud equivalent, test type)
- Licence: Norwegian Licence for Open Government Data (NLOD 2.0) —
  https://www.sodir.no/en/facts/data-and-analyses/open-data/
  (free reuse with attribution to the Norwegian Offshore Directorate)
- Refresh: re-run the query; first rows are stable by OBJECTID but the
  underlying WDSS table is updated as wells are released.

What it is: casing-shoe LOT/FIT mud weights (g/cm³ equivalent), mostly
shallow (median casing depth ~1500 m in this subset). It constrains the
fracture-gradient trend used as a sanity anchor for the default
`shmin_gradient` assumption — NOT a substitute for a well-specific LOT,
XLOT or DFIT at reservoir depth.
