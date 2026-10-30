# Physics validation

Run:

```bash
python scripts/validate_physics.py
```

The script has no API or database dependency. It checks:

| Check | Expected |
|---|---|
| IBM float | `0x41100000` = 1.0, `0xC1100000` = -1.0 |
| Constant depth | 2000 ms at 2500 m/s = 2500 m |
| Layer depth | 1500 ms through 2000/3000 m/s layers = 1750 m |
| GRV base | 50 m column over 4 × 25 × 25 m cells = 125,000 m³ |
| Fault geometry | 8 ms TWT throw at 2500 m/s = 10 m; 10 m/25 m = 21.801° |
| Shaly sand | Clean-sand Simandoux and Indonesian equal Archie |
| Field LAS | TWT integral matches DT-depth integration on Hawkins and KGS fixtures |
| GRV contract | Trace labels never scale area; `[0, 25]` m and `[100, 101]` labels both give 625 m² cells |
| Kriging | Exact at sample nodes with zero nugget; all three variogram models |
| Kirchhoff | Per-voxel fold; aperture-cut and dead traces carry zero fold |

The field checks validate units, TWT integration and finite synthetic traces.
They are **not** a substitute for checkshot-calibrated field ties or reserves
audit. The fixtures are public LAS files; no confidential field data is stored.

The same checks are in `tests/test_physics_benchmarks.py`, so CI runs them.
