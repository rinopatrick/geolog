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
  for (const v of views) {
    await page.evaluate((x)=>window.app && app.switchView(x), v);
    await page.waitForTimeout(80);
  }
  const out = { views: views.length, js_errors: errors.length, errors };
  console.log(JSON.stringify(out,null,2));
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})();
