# Panel Inventory (1.0 hardening prototype artifact)

Generated from code, not from screenshots. Method: nav buttons in
`frontend/index.html` vs dispatch lines in `frontend/js/app.js` `switchView`,
plus per-panel load action on view entry.

## Counts

- Nav buttons: 46
- Dispatch panels: 46
- In dispatch not nav: none
- In nav not dispatch: none

## Load behavior on view entry

Auto-load on entry: matrix, audit, users, jobmonitor, seismic, reportbuilder,
crossplot, pickett, mnplot, petrophysics, qc, correlation, statistics,
comparison, tools, production, facies, striplog, probability, moveable,
dipplot, buckles, hingle, datatable, topsmgmt, formation, map, dashboard,
multiwell, formationtester.

Gated on current well: advancedqc, zonation, units, templates.

Gated on module presence: corescal (CoreScalView), geomechanics
(GeomechanicsView), imagelog (ImageLogView).

User-triggered inside panel (button, not view entry): vclmodels
(`runVclModels`), corecal (`showCoreCalModal`), qcautofix (`runQcAutofix`),
sensitivity (auto-loads on click), calculator (form), batch (form),
tornado (run button in petrophysics panel).

Module files own the rest: app-correlation, app-data, app-map, app-petro,
app-reports, app-segy, core-scal, geomechanics, image-log, qc, zonation,
correlation, log-renderer.

## 1.0 fix list (bounded)

1. No orphan panels at dispatch level. No fix.
2. No dead nav entries. No fix.
3. Dead error states not proven by static read. Needs runtime pass per panel
   with empty, loading, error states via better-interface before any polish.
4. Copy consistency and destructive action confirmations need the same runtime
   pass with better-writing. No static finding claimed.

## Verification

- `BORELIA_ENV=test BORELIA_DB_PATH=/tmp/probe-test.db` import of
  `backend.main` plus regex over `frontend/index.html` and
  `frontend/js/app.js` produced the counts above.
- Runtime panel pass is fog until the migration drill ticket resolves.
