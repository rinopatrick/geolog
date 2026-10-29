# DLIS/LIS regression fixtures

These files come from the public test-data directory of
[equinor/dlisio](https://github.com/equinor/dlisio), retrieved on 2026-10-29.

| File | Origin | Purpose |
|---|---|---|
| `206_05a-_3_DWL_DWL_WIRE_258276498.DLIS` | `python/data/` | Actual produced DLIS file used for strict parser regression |
| `MUD_LOG_1.LIS` | `python/data/lis/` | LIS file used to exercise the LIS reader and fallback path |

`LICENSE.dlisio` is the upstream LGPL-3.0 license. The files are test data and
are not linked into the application. Include this notice and license when
redistributing the fixtures.
