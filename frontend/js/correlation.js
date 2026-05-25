const DEFAULTS = {
  trackWidth: 150,
  trackGap: 42,
  topMargin: 24,
  bottomMargin: 24,
  leftMargin: 28,
  rightMargin: 28,
};

function finite(v) {
  return Number.isFinite(v) ? v : null;
}

function nearestBy(arr, getter, value, tolerance = 10) {
  let best = null;
  let bestDelta = Number.POSITIVE_INFINITY;
  for (const item of arr || []) {
    const d = Number(getter(item));
    if (!Number.isFinite(d)) continue;
    const delta = Math.abs(d - value);
    if (delta < bestDelta && delta <= tolerance) {
      best = item;
      bestDelta = delta;
    }
  }
  return best;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

class CrossSectionRenderer {
  constructor(canvas, options = {}) {
    if (!canvas) throw new Error('CrossSectionRenderer requires a canvas element');
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.options = { ...DEFAULTS, ...options };
    this.data = { wells: [], depth_range: { min: 0, max: 1000 }, curve: 'GR' };
    this.previewTransform = new Map(); // well_id -> {shift, stretch}
    this.onRender = null;
  }

  setData(crossSectionData) {
    this.data = crossSectionData || this.data;
    this.render();
  }

  setPreviewTransform(wellId, shift = 0, stretch = 1) {
    this.previewTransform.set(Number(wellId), { shift: Number(shift) || 0, stretch: Number(stretch) || 1 });
    this.render();
  }

  clearPreviewTransform(wellId) {
    this.previewTransform.delete(Number(wellId));
    this.render();
  }

  clearAllPreviewTransforms() {
    this.previewTransform.clear();
    this.render();
  }

  getDepthRange() {
    const d = this.data?.depth_range || {};
    const min = Number(d.min);
    const max = Number(d.max);
    if (Number.isFinite(min) && Number.isFinite(max) && max > min) return { min, max };

    const allDepths = (this.data?.wells || []).flatMap(w => w.depth || []).filter(Number.isFinite);
    if (!allDepths.length) return { min: 0, max: 1000 };
    return { min: Math.min(...allDepths), max: Math.max(...allDepths) };
  }

  depthToY(depth) {
    const { min, max } = this.getDepthRange();
    const h = this.canvas.height - this.options.topMargin - this.options.bottomMargin;
    const t = (depth - min) / Math.max(max - min, 1e-6);
    return this.options.topMargin + t * h;
  }

  yToDepth(y) {
    const { min, max } = this.getDepthRange();
    const h = this.canvas.height - this.options.topMargin - this.options.bottomMargin;
    const t = (y - this.options.topMargin) / Math.max(h, 1e-6);
    return min + t * (max - min);
  }

  getTrackLayout() {
    const wells = this.data?.wells || [];
    const { leftMargin, rightMargin, trackGap } = this.options;
    const fullW = this.canvas.width - leftMargin - rightMargin;
    const count = Math.max(wells.length, 1);
    const trackWidth = Math.max(90, (fullW - (count - 1) * trackGap) / count);

    return wells.map((w, i) => {
      const x = leftMargin + i * (trackWidth + trackGap);
      return { well: w, wellId: Number(w.well_id), x, width: trackWidth, center: x + trackWidth / 2 };
    });
  }

  _applyDepthTransform(track, depth) {
    const t = this.previewTransform.get(Number(track.wellId));
    if (!t) return depth;
    return (depth * t.stretch) + t.shift;
  }

  _drawCurveTrack(track) {
    const { ctx } = this;
    const depth = track.well.depth || [];
    const values = track.well.values || [];
    if (!depth.length || !values.length) return;

    const finiteVals = values.filter(Number.isFinite);
    if (!finiteVals.length) return;

    const vMin = Math.min(...finiteVals);
    const vMax = Math.max(...finiteVals);
    const span = Math.max(vMax - vMin, 1e-9);

    ctx.save();
    ctx.strokeStyle = '#9fb4d9';
    ctx.lineWidth = 1.2;
    ctx.beginPath();

    let started = false;
    for (let i = 0; i < Math.min(depth.length, values.length); i++) {
      const d = Number(depth[i]);
      const v = Number(values[i]);
      if (!Number.isFinite(d) || !Number.isFinite(v)) continue;
      const td = this._applyDepthTransform(track, d);
      const y = this.depthToY(td);
      const nx = (v - vMin) / span;
      const x = track.x + lerp(0, track.width, nx);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();

    // fill toward track left for visual cross-section body
    ctx.globalAlpha = 0.16;
    ctx.fillStyle = '#4c82d9';
    ctx.beginPath();
    started = false;
    for (let i = 0; i < Math.min(depth.length, values.length); i++) {
      const d = Number(depth[i]);
      const v = Number(values[i]);
      if (!Number.isFinite(d) || !Number.isFinite(v)) continue;
      const td = this._applyDepthTransform(track, d);
      const y = this.depthToY(td);
      const nx = (v - vMin) / span;
      const x = track.x + lerp(0, track.width, nx);
      if (!started) {
        ctx.moveTo(track.x, y);
        ctx.lineTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.strokeStyle = 'transparent';
    ctx.lineTo(track.x, this.depthToY(this._applyDepthTransform(track, depth[depth.length - 1])));
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.strokeStyle = '#52606d';
    ctx.strokeRect(track.x, this.options.topMargin, track.width, this.canvas.height - this.options.topMargin - this.options.bottomMargin);

    ctx.fillStyle = '#dbe7ff';
    ctx.font = '12px sans-serif';
    ctx.fillText(track.well.well_name || `Well ${track.wellId}`, track.x, this.options.topMargin - 8);

    ctx.restore();
  }

  _drawFormationTopSpans(layout) {
    const { ctx } = this;
    const formationDepths = new Map();

    for (const track of layout) {
      for (const t of track.well.tops || []) {
        const name = String(t.formation_name || '').trim();
        const d = Number(t.depth);
        if (!name || !Number.isFinite(d)) continue;
        if (!formationDepths.has(name)) formationDepths.set(name, []);
        formationDepths.get(name).push({ track, depth: this._applyDepthTransform(track, d), color: t.color || '#888' });
      }
    }

    ctx.save();
    ctx.lineWidth = 1;
    ctx.font = '11px sans-serif';

    for (const [name, points] of formationDepths.entries()) {
      if (points.length < 2) continue;
      points.sort((a, b) => a.track.x - b.track.x);
      const avgDepth = points.reduce((s, p) => s + p.depth, 0) / points.length;
      const y = this.depthToY(avgDepth);
      const c = points[0].color || '#7d8ca3';
      ctx.strokeStyle = c;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(points[0].track.x, y);
      ctx.lineTo(points[points.length - 1].track.x + points[points.length - 1].track.width, y);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = c;
      ctx.fillText(name, points[0].track.x + 4, y - 4);
    }

    ctx.restore();
  }

  render() {
    const { ctx, canvas } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#0f1724';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const layout = this.getTrackLayout();
    layout.forEach(track => this._drawCurveTrack(track));
    this._drawFormationTopSpans(layout);

    if (typeof this.onRender === 'function') this.onRender({ layout, renderer: this });
    return layout;
  }
}

class TieLineOverlay {
  constructor(renderer, options = {}) {
    this.renderer = renderer;
    this.options = {
      color: '#f59e0b',
      markerColor: '#ffde99',
      lineWidth: 1.2,
      ...options,
    };
    this.tieLines = [];
  }

  setTieLines(tieLines = []) {
    this.tieLines = Array.isArray(tieLines) ? tieLines : [];
    this.renderer.render();
  }

  draw(layout) {
    const ctx = this.renderer.ctx;
    const tracksById = new Map(layout.map(t => [Number(t.wellId), t]));

    ctx.save();
    ctx.lineWidth = this.options.lineWidth;

    for (const tl of this.tieLines) {
      const wa = tracksById.get(Number(tl.well_a_id));
      const wb = tracksById.get(Number(tl.well_b_id));
      const aDepth = Number(tl.a_depth);
      const bDepth = Number(tl.b_depth);
      if (!wa || !wb || !Number.isFinite(aDepth) || !Number.isFinite(bDepth)) continue;

      const ya = this.renderer.depthToY(this.renderer._applyDepthTransform(wa, aDepth));
      const yb = this.renderer.depthToY(this.renderer._applyDepthTransform(wb, bDepth));
      const xa = wa.x + wa.width;
      const xb = wb.x;

      ctx.strokeStyle = tl.color || this.options.color;
      ctx.beginPath();
      ctx.moveTo(xa, ya);
      ctx.lineTo(xb, yb);
      ctx.stroke();

      ctx.fillStyle = this.options.markerColor;
      ctx.beginPath();
      ctx.arc(xa, ya, 2.8, 0, Math.PI * 2);
      ctx.arc(xb, yb, 2.8, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  }

  attach() {
    const prev = this.renderer.onRender;
    this.renderer.onRender = (evt) => {
      if (typeof prev === 'function') prev(evt);
      this.draw(evt.layout);
    };
    this.renderer.render();
  }
}

class MarkerSnapping {
  constructor({ tolerance = 8 } = {}) {
    this.tolerance = tolerance;
  }

  snapByDepth(sourceDepth, sourceTops = [], targetTops = []) {
    const sd = Number(sourceDepth);
    if (!Number.isFinite(sd)) return null;

    const src = nearestBy(sourceTops, t => Number(t.depth), sd, this.tolerance);
    if (!src) return null;

    const srcName = String(src.formation_name || src.name || '').trim().toLowerCase();
    let target = null;

    if (srcName) {
      target = (targetTops || []).find(t => String(t.formation_name || t.name || '').trim().toLowerCase() === srcName) || null;
    }

    if (!target) {
      target = nearestBy(targetTops, t => Number(t.depth), sd, Number.POSITIVE_INFINITY);
    }

    if (!target) return null;

    return {
      sourceTop: src,
      targetTop: target,
      sourceDepth: finite(Number(src.depth)),
      targetDepth: finite(Number(target.depth)),
      label: src.formation_name || src.name || target.formation_name || target.name || 'Snapped',
    };
  }
}

class ShiftStretchControls {
  constructor({ shiftInput, stretchInput, renderer, targetWellId, onPreview } = {}) {
    this.shiftInput = shiftInput;
    this.stretchInput = stretchInput;
    this.renderer = renderer;
    this.targetWellId = Number(targetWellId);
    this.onPreview = onPreview;
    this._bound = false;
  }

  _applyPreview() {
    const shift = Number(this.shiftInput?.value || 0);
    const stretch = Number(this.stretchInput?.value || 1);
    const s = Number.isFinite(stretch) && stretch !== 0 ? stretch : 1;

    if (this.renderer && Number.isFinite(this.targetWellId)) {
      this.renderer.setPreviewTransform(this.targetWellId, Number.isFinite(shift) ? shift : 0, s);
    }
    if (typeof this.onPreview === 'function') {
      this.onPreview({ shift: Number.isFinite(shift) ? shift : 0, stretch: s, wellId: this.targetWellId });
    }
  }

  bind() {
    if (this._bound) return;
    const handler = () => this._applyPreview();
    this._handler = handler;
    this.shiftInput?.addEventListener('input', handler);
    this.stretchInput?.addEventListener('input', handler);
    this._bound = true;
    this._applyPreview();
  }

  unbind() {
    if (!this._bound) return;
    this.shiftInput?.removeEventListener('input', this._handler);
    this.stretchInput?.removeEventListener('input', this._handler);
    this._bound = false;
  }

  commit() {
    this._applyPreview();
    return {
      shift: Number(this.shiftInput?.value || 0) || 0,
      stretch: Number(this.stretchInput?.value || 1) || 1,
      wellId: this.targetWellId,
    };
  }
}

async function fetchCrossSection(baseUrl, wellIds = [], curve = 'GR') {
  const ids = (wellIds || []).map(Number).filter(Number.isFinite);
  const qs = new URLSearchParams({ well_ids: ids.join(','), curve });
  const r = await fetch(`${baseUrl}/api/correlation/cross-section?${qs.toString()}`);
  if (!r.ok) throw new Error(`Cross-section fetch failed: ${r.status}`);
  return r.json();
}

async function fetchTieLines(baseUrl, wellAId, wellBId) {
  const qs = new URLSearchParams({ well_a_id: String(wellAId), well_b_id: String(wellBId) });
  const r = await fetch(`${baseUrl}/api/correlation/tie-lines?${qs.toString()}`);
  if (!r.ok) throw new Error(`Tie-lines fetch failed: ${r.status}`);
  return r.json();
}

async function autoCorrelate(baseUrl, payload) {
  const r = await fetch(`${baseUrl}/api/correlation/auto-correlate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  if (!r.ok) throw new Error(`Auto-correlate failed: ${r.status}`);
  return r.json();
}
