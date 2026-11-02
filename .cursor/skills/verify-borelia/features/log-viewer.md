# Log viewer

## Sub-features

- 4-track canvas viewer (GR/SP/CAL, resistivity, porosity, saturation).
- Scroll zoom, drag pan, depth ruler, hover readout, tops/zones overlay.

## How to get to it (user POV)

Open app `/` → viewer panel → select well with curves → tracks render.
`app.switchView('viewer')` selects it programmatically.

## Driving it with Playwright

```js
await page.goto(base, { waitUntil: 'domcontentloaded' });
const ok = await page.evaluate(() => { app.switchView('viewer'); return true; });
// pick first well via UI or: await page.evaluate(() => app.selectWell?.(wellId));
await page.screenshot({ path: 'artifacts/verify/<ts>/viewer.png' });
const tracks = await page.evaluate(() => document.querySelectorAll('canvas').length);
```

## Gotchas

- Viewer needs a well WITH curves; upload one first (see well-upload.md).
  Panels auto-fetch on `switchView`: probability/moveable/hingle return 404
  "Required curves not found" unless the well carries that panel's curves.
- Console errors fail the run (`scripts/e2e_panel_smoke.js` pattern: listen for
  `pageerror` + console `error`). Expect the 3 auto-fetch 404s above on a KGS-sample
  DB; green smoke needs wells with the panels' default curves.
- Canvas content can't be asserted via DOM; assert curve data via API
  (`GET /api/log-runs/{id}/curves`) alongside the screenshot.
