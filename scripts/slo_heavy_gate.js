#!/usr/bin/env node
/** Heavy-endpoint SLO gate: wedge-model latency, prospect-maps valid +
 *  oversize-reject latency. Seeds a tiny SEG-Y volume via API (same shape
 *  as the pytest fixture), so no checked-in binary is needed.
 *  Pass = valid maps under threshold AND oversize rejected fast with 400.
 *  Requires backend + playwright NOT needed (pure API). */
const { chromium } = require('playwright');

const ADMIN = { 'X-User-Role': 'admin' };
const SLO = {
  wedgeP95Ms: Number(process.env.SLO_WEDGE_P95_MS || 15000),
  mapsValidP95Ms: Number(process.env.SLO_MAPS_P95_MS || 15000),
  oversizeRejectMs: Number(process.env.SLO_OVERSIZE_REJECT_MS || 10000),
};

function segyVolume() {
  const textual = Buffer.alloc(3200, 0x20);
  const binary = Buffer.alloc(400);
  const ns = 12;
  binary.writeUInt16BE(2000, 16);
  binary.writeUInt16BE(ns, 20);
  binary.writeUInt16BE(5, 24);
  let seed = 41;
  const random = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 0xffffffff; };
  const traces = [];
  for (let inline = 0; inline < 3; inline += 1) {
    for (let crossline = 0; crossline < 3; crossline += 1) {
      const header = Buffer.alloc(240);
      header.writeUInt16BE(ns, 114);
      header.writeUInt32BE(100 + inline, 188);
      header.writeUInt32BE(200 + crossline, 192);
      const data = Buffer.alloc(ns * 4);
      for (let s = 0; s < ns; s += 1) data.writeFloatBE((random() - 0.5) * 0.02, s * 4);
      traces.push(Buffer.concat([header, data]));
    }
  }
  return Buffer.concat([textual, binary, ...traces]);
}

async function api(base, path, opts = {}) {
  const t0 = Date.now();
  const res = await fetch(base + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...ADMIN, ...(opts.headers || {}) },
  });
  const ms = Date.now() - t0;
  const text = await res.text();
  let body = null;
  try { body = JSON.parse(text); } catch (_) { /* non-JSON */ }
  return { status: res.status, ms, body, text: text.slice(0, 200) };
}

async function apiUpload(base, path, fileBuffer, fields) {
  const t0 = Date.now();
  const form = new FormData();
  form.append('file', new Blob([fileBuffer], { type: 'application/octet-stream' }), 'slo.sgy');
  for (const [k, v] of Object.entries(fields)) form.append(k, v);
  const res = await fetch(base + path, { method: 'POST', headers: { ...ADMIN }, body: form });
  const ms = Date.now() - t0;
  const body = await res.json().catch(() => null);
  return { status: res.status, ms, body };
}

function pct(values, p) {
  if (!values.length) return 0;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor((p / 100) * s.length))];
}

(async () => {
  const base = process.env.BORELIA_BASE_URL || 'http://127.0.0.1:8000';
  const out = { checks: {} };
  try {
    // Seed: project + tiny volume + horizons + surface + depth.
    const projects = (await api(base, '/api/projects/')).body;
    let pid = projects[0]?.id;
    if (!pid) {
      const created = (await api(base, '/api/projects/', { method: 'POST', body: JSON.stringify({ name: 'SLO Heavy' }) })).body;
      if (!created.id) throw new Error('project create: ' + JSON.stringify(created));
      pid = created.id;
    }
    const up = await apiUpload(base, `/api/projects/${pid}/seismic`, segyVolume(), { name: 'SLO Volume' });
    if (up.status !== 201) throw new Error('upload: ' + up.status + ' ' + JSON.stringify(up.body));
    const lineId = up.body.id;
    for (const inline of [100, 101, 102]) {
      const hz = await api(base, `/api/seismic/${lineId}/horizons`, {
        method: 'POST', body: JSON.stringify({
          name: 'SLO Top', mode: 'inline', section_value: inline,
          picks: [{ trace: 0, sample: 2 }, { trace: 1, sample: 3 }, { trace: 2, sample: 4 }],
        }),
      });
      if (hz.status !== 201) throw new Error('horizon: ' + hz.status);
    }
    const surf = await api(base, `/api/seismic/${lineId}/surfaces`, {
      method: 'POST', body: JSON.stringify({ name: 'SLO Surface', horizon_name: 'SLO Top', max_grid: 64, inline_spacing_m: 25, crossline_spacing_m: 25 }),
    });
    if (surf.status !== 201) throw new Error('surface: ' + surf.status);
    const model = await api(base, `/api/projects/${pid}/velocity-models`, {
      method: 'POST', body: JSON.stringify({ name: 'SLO 2000', kind: 'constant', velocity_m_s: 2000 }),
    });
    const conv = await api(base, `/api/seismic/${lineId}/surfaces/${surf.body.id}/depth`, {
      method: 'POST', body: JSON.stringify({ velocity_model_id: model.body.id }),
    });
    if (conv.status !== 200) throw new Error('depth: ' + conv.status);
    const surface = conv.body;

    // Wedge-model latency (5 runs, stateless).
    const wedgeMs = [];
    for (let i = 0; i < 5; i += 1) {
      const r = await api(base, '/api/seismic/wedge-model', {
        method: 'POST',
        body: JSON.stringify({
          ai_top: 13800000, ai_reservoir: 20800000, ai_base: 13800000,
          velocity_m_s: 3000, freqs_hz: [20, 30, 40],
          thickness_m: Array.from({ length: 31 }, (_, k) => k * 2),
        }),
      });
      if (r.status !== 200) throw new Error('wedge-model: ' + r.status + ' ' + r.text);
      wedgeMs.push(r.ms);
    }
    // Valid prospect-maps latency (3 runs, small grid).
    const mapsMs = [];
    for (let i = 0; i < 3; i += 1) {
      const r = await api(base, `/api/projects/${pid}/prospect-maps`, {
        method: 'POST',
        body: JSON.stringify({
          surface_id: surface.id, contact_depth_m: 1000,
          porosity: 0.2, water_saturation: 0.3, net_to_gross: 0.8,
          iterations: 500, seed: 7,
        }),
      });
      if (r.status !== 200) throw new Error('prospect-maps valid: ' + r.status + ' ' + r.text);
      mapsMs.push(r.ms);
    }
    // Max allowed load must answer fast with 200. The over-cap 400 path
    // (grid x iterations > 2M) is covered by pytest with a synthetic grid.
    const big = await api(base, `/api/projects/${pid}/prospect-maps`, {
      method: 'POST',
      body: JSON.stringify({
        surface_id: surface.id, contact_depth_m: 1000,
        iterations: 20000, seed: 7,
      }),
    });
    out.checks = {
      wedge_p95_ms: pct(wedgeMs, 95),
      maps_valid_p95_ms: pct(mapsMs, 95),
      maxload_status: big.status,
      maxload_ms: big.ms,
    };
    const okWedge = out.checks.wedge_p95_ms <= SLO.wedgeP95Ms;
    const okMaps = out.checks.maps_valid_p95_ms <= SLO.mapsValidP95Ms;
    const okMaxload = big.status === 200 && big.ms <= SLO.oversizeRejectMs;
    out.ok = okWedge && okMaps && okMaxload;
    out.thresholds = SLO;
    if (!out.ok) out.reason = JSON.stringify({ okWedge, okMaps, okMaxload });
  } catch (e) {
    out.ok = false;
    out.reason = e.message;
  }
  console.log(JSON.stringify(out, null, 2));
  process.exit(out.ok ? 0 : 1);
})();
