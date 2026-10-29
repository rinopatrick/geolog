#!/usr/bin/env node
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type()==='error') errors.push(m.text()); });
  const base = process.env.GEOLOG_BASE_URL || 'http://localhost:8000';
  await page.goto(base, { waitUntil: 'domcontentloaded' });

  const dedupeOk = await page.evaluate(async () => {
    try {
      const path = '/correlation-profile?well_a_id=1&well_b_id=2';
      const [a, b] = await Promise.all([app._api(path), app._api(path)]);
      return JSON.stringify(a) === JSON.stringify(b);
    } catch (_) { return false; }
  });

  const actionOk = await page.evaluate(() => {
    let called = 0;
    app._e2eAction = () => { called += 1; };
    const button = document.createElement('button');
    button.dataset.action = 'app._e2eAction';
    document.body.appendChild(button);
    button.click();
    button.remove();
    delete app._e2eAction;
    return called === 1;
  });

  const views = ['viewer','crossplot','pickett','mnplot','petrophysics','qc','correlation','statistics','sensitivity','comparison','tools','production','facies','striplog','probability','moveable','dipplot','buckles','hingle','calculator','datatable','topsmgmt','formation','batch','map','dashboard','matrix','audit','tornado','vclmodels','corecal','corescal','geomechanics','qcautofix','seismic','imagelog','analogs','users','jobmonitor','reportbuilder'];

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
  const out = { ok: switched === views.length && errors.length === 0 && dedupeOk && actionOk, views: views.length, switched, dedupe_ok: dedupeOk, action_ok: actionOk, js_errors: errors.length, errors };
  console.log(JSON.stringify(out,null,2));
  await browser.close();
  process.exit(out.ok ? 0 : 1);
})();
