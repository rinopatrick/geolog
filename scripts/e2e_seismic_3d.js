#!/usr/bin/env node
/**
 * Browser smoke for 3D SEG-Y: upload, volume selectors, inline/crossline
 * sections and 3D fault linkage. Requires the demo seed and playwright.
 */
const { chromium } = require('playwright');

function buildVolume() {
  const nInlines = 6;
  const nCrosslines = 48;
  const ns = 40;
  const textual = Buffer.alloc(3200, 0x20);
  const binary = Buffer.alloc(400);
  binary.writeUInt16BE(2000, 16);
  binary.writeUInt16BE(ns, 20);
  binary.writeUInt16BE(5, 24);
  const traces = [];
  let seed = 11;
  const random = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 0xffffffff;
  };
  for (let inline = 0; inline < nInlines; inline += 1) {
    for (let crossline = 0; crossline < nCrosslines; crossline += 1) {
      const header = Buffer.alloc(240);
      header.writeUInt16BE(ns, 114);
      header.writeUInt32BE(100 + inline, 188);
      header.writeUInt32BE(200 + crossline, 192);
      const data = Buffer.alloc(ns * 4);
      const center = crossline < 24 ? 10 : 14;
      for (let sample = 0; sample < ns; sample += 1) {
        const distance = Math.abs(sample - center);
        const event = distance <= 2 ? [0.1, 0.5, 1.0, 0.5, 0.1][distance] : 0;
        data.writeFloatBE((random() - 0.5) * 0.01 + event, sample * 4);
      }
      traces.push(Buffer.concat([header, data]));
    }
  }
  return Buffer.concat([textual, binary, ...traces]);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const base = process.env.GEOLOG_BASE_URL || 'http://127.0.0.1:8010';
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  const encoded = buildVolume().toString('base64');
  const result = await page.evaluate(async (base64) => {
    try {
      const bytes = Uint8Array.from(atob(base64), char => char.charCodeAt(0));
      const file = new File([bytes], 'e2e-volume.sgy', { type: 'application/octet-stream' });
      await app.loadProjects();
      const projectId = app._segyProjectId();
      if (!projectId) return { ok: false, reason: 'no project' };
      const form = new FormData();
      form.append('file', file);
      form.append('name', 'E2E 3D Volume');
      const line = await app._api(`/projects/${projectId}/seismic`, { method: 'POST', body: form });
      await app.loadSeismicLines();
      await app.loadSeismicLine(line.id);
      const volumeOk = app._segyVolume?.is_3d === true
        && document.querySelectorAll('#segyInlineSelect option').length === 6
        && document.querySelectorAll('#segyCrosslineSelect option').length === 48;
      await app.loadSeismicVolumeSection('inline', 100);
      const inlineOk = app._segySection?.mode === 'inline' && app._segySection.labels[0] === 200;
      await app.loadSeismicVolumeSection('inline', 100);
      app._segyPicks = [{ trace: 2, sample: 10 }];
      await app.saveSeismicHorizon();
      const horizonOk = (app._segyHorizons || []).some(h => h.mode === 'inline' && h.section_value === 100);
      await app.loadSeismicVolumeSection('inline', 100);
      app._segyPicks = [{ trace: 10, sample: 10 }];
      await app.autoTrackSeismic();
      const autoTrackOk = (app._segyHorizons || []).some(h => h.mode === 'inline' && h.picks.length >= 20);
      await app.loadSeismicVolumeSection('crossline', 247);
      const crosslineOk = app._segySection?.mode === 'crossline' && app._segySection.labels.length === 6;
      document.getElementById('segyInlineSpacing').value = '25';
      document.getElementById('segyCrosslineSpacing').value = '25';
      await app.linkSeismicFaults3D();
      const geometry = app._segyFaultLinks?.[0]?.geometry || {};
      const geometryOk = geometry.throw_ms > 0 && geometry.dip_angle_deg != null;
      return {
        ok: volumeOk && inlineOk && crosslineOk && horizonOk && autoTrackOk && geometryOk && (app._segyFaultLinks || []).length > 0,
        lineId: line.id,
        volumeOk,
        inlineOk,
        crosslineOk,
        horizonOk,
        autoTrackOk,
        geometryOk,
        throwMs: geometry.throw_ms,
        dipAngle: geometry.dip_angle_deg,
        polygonPoints: (app._segyFaultLinks?.[0]?.polygon || []).length,
        links: (app._segyFaultLinks || []).length,
        sectionMode: app._segySection?.mode,
        status: document.getElementById('segyStatus')?.textContent || '',
      };
    } catch (error) {
      return { ok: false, reason: error.message };
    }
  }, encoded);
  const out = { ...result, js_errors: errors.length, errors };
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
  process.exit(out.ok && errors.length === 0 ? 0 : 1);
})();
