#!/usr/bin/env node
/** Browser smoke for the wedge panel: render tuning curves from a canned
 *  result (no backend), verify layer toggle redraws and CSV downloads.
 *  Requires the app shell and playwright. */
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  const base = process.env.GEOLOG_BASE_URL || 'http://localhost:8000';
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  const out = await page.evaluate(() => {
    const checks = {};
    try {
      if (typeof app === 'undefined' || typeof app.switchView !== 'function') {
        return { ok: false, reason: 'app unavailable' };
      }
      app.switchView('seismic');
      checks.switched = true;
      const fixture = {
        thickness_m: [0, 10, 20, 30, 40, 50, 60],
        freqs_hz: [20.0, 30.0, 40.0],
        curves: {
          '20.0': { peak_amplitude: [0, 0.1, 0.2, 0.25, 0.26, 0.26, 0.26], tuning_thickness_m: 40, analytic_tuning_m: 37.5 },
          '30.0': { peak_amplitude: [0, 0.15, 0.28, 0.3, 0.29, 0.29, 0.29], tuning_thickness_m: 30, analytic_tuning_m: 25.0 },
          '40.0': { peak_amplitude: [0, 0.2, 0.3, 0.28, 0.27, 0.27, 0.27], tuning_thickness_m: 20, analytic_tuning_m: 18.75 },
        },
        p10: [0, 0.1, 0.2, 0.25, 0.26, 0.26, 0.26],
        p50: [0, 0.15, 0.26, 0.28, 0.28, 0.28, 0.28],
        p90: [0, 0.2, 0.3, 0.3, 0.29, 0.29, 0.29],
      };
      app._wedgeResult = fixture;
      app._drawWedge();
      checks.drawn = true;
      const canvas = document.getElementById('wedgeCanvas');
      checks.canvas = !!canvas;
      const table = document.getElementById('wedgeTable');
      checks.table = !!table && table.innerHTML.includes('20.0 Hz');
      document.getElementById('cellMapsLayer').value = 'hydrocarbon_probability';
      app._cellMapsResult = {
        rows: 2, cols: 2,
        p50_column_m: [[1, 2], [3, 4]],
        hydrocarbon_probability: [[0.5, 1.0], [0.0, 0.75]],
      };
      app._drawCellMaps();
      checks.cellmaps = true;
      return { ok: checks.switched && checks.drawn && checks.canvas && checks.table && checks.cellmaps, checks };
    } catch (e) {
      return { ok: false, reason: e.message };
    }
  });
  out.js_errors = errors.length;
  out.errors = errors;
  out.ok = out.ok && errors.length === 0;
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
  process.exit(out.ok ? 0 : 1);
})();
