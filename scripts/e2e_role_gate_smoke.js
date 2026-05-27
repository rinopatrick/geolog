#!/usr/bin/env node
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];

  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => {
    if (m.type() === 'error') errors.push(m.text());
  });

  await page.goto('http://localhost:8000', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(400);

  const roles = ['viewer', 'interpreter', 'admin'];
  const stats = {};

  for (const role of roles) {
    const s = await page.evaluate((r) => {
      if (typeof app === 'undefined' || typeof app.setActiveRole !== 'function') {
        return { role: r, error: 'app.setActiveRole unavailable' };
      }
      app.setActiveRole(r);
      const all = [...document.querySelectorAll('[data-role-required]')];
      const disabled = all.filter(el => !!el.disabled).length;
      return {
        role: r,
        gated_total: all.length,
        gated_disabled: disabled,
      };
    }, role);
    stats[role] = s;
  }

  const viewer = stats.viewer?.gated_disabled ?? -1;
  const interpreter = stats.interpreter?.gated_disabled ?? -1;
  const admin = stats.admin?.gated_disabled ?? -1;
  const gatedTotal = stats.viewer?.gated_total ?? 0;

  const checks = {
    app_available: !Object.values(stats).some(s => s.error),
    gated_elements_present: gatedTotal > 0,
    monotonic_permissions: viewer >= interpreter && interpreter >= admin,
    viewer_has_some_locks: viewer > 0,
  };

  const ok = Object.values(checks).every(Boolean) && errors.length === 0;

  const out = { ok, checks, stats, js_errors: errors.length, errors };
  console.log(JSON.stringify(out, null, 2));

  await browser.close();
  process.exit(ok ? 0 : 1);
})();
