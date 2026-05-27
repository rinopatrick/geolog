#!/usr/bin/env node
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type()==='error') errors.push(m.text()); });
  await page.goto('http://localhost:8000', { waitUntil: 'domcontentloaded' });

  const views = ['viewer','crossplot','pickett','mnplot','petrophysics','qc','correlation','statistics','sensitivity','comparison','tools','production','facies','striplog','probability','moveable','dipplot','buckles','hingle','calculator','datatable','topsmgmt','formation','batch','map','dashboard','matrix','audit','tornado','vclmodels','corecal','qcautofix','seismic','imagelog','analogs','users','jobmonitor'];

  const appAvailable = await page.evaluate(() => typeof app !== 'undefined' && typeof app.switchView === 'function');
  if (!appAvailable) {
    console.log(JSON.stringify({ ok: false, reason: 'app.switchView unavailable', js_errors: errors.length, errors }, null, 2));
    await browser.close();
    process.exit(1);
  }

  let switched = 0;
  for (const v of views) {
    const ok = await page.evaluate((x) => {
      try { app.switchView(x); return true; } catch (_) { return false; }
    }, v);
    if (ok) switched += 1;
    await page.waitForTimeout(80);
  }
  const out = { ok: switched === views.length && errors.length === 0, views: views.length, switched, js_errors: errors.length, errors };
  console.log(JSON.stringify(out,null,2));
  await browser.close();
  process.exit(out.ok ? 0 : 1);
})();
