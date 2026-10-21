/* Geomechanics screening workbench. Curves come from the shared semantics layer. */
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (v, d = 1) => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d);
  const badgeClass = (v) => v === 'calibrated' || v === 'measured' ? 'px-info' : v === 'assumption' ? 'px-warn' : '';

  const View = {
    state: { wid: null, models: [], selectedId: null, model: null, result: null, busy: false },

    async load() {
      if (!app.currentWell) return;
      this.state.wid = app.currentWell.id;
      try {
        const models = await app._api(`/wells/${this.state.wid}/geomechanics/models`);
        this.state.models = models;
        if (this.state.selectedId && !models.some((m) => m.id === this.state.selectedId)) this.state.selectedId = null;
        if (!this.state.selectedId && models.length) this.state.selectedId = models[0].id;
        this.state.model = models.find((m) => m.id === this.state.selectedId) || null;
        this.renderModels();
        if (this.state.model) await this.compute(false);
        else this.renderEmpty();
      } catch (e) { GeoToast.error(`Geomechanics: ${e.message}`); }
    },

    params() {
      return {
        mud_weight: Number($('geoMudWeight')?.value || 9),
        shmax_azimuth: Number($('geoAzimuth')?.value || 0),
        shmin_gradient: Number($('geoShminGrad')?.value || 0.7),
        shmax_gradient: Number($('geoShmaxGrad')?.value || 1.2),
      };
    },

    renderModels() {
      const select = $('geoModel');
      select.innerHTML = this.state.models.length
        ? this.state.models.map((m) => `<option value="${m.id}" ${m.id === this.state.selectedId ? 'selected' : ''}>Model v${esc(m.version)} · ${esc(m.status)}</option>`).join('')
        : '<option value="">No model</option>';
      this.renderBadges();
      if (this.state.model) {
        const p = this.state.model.params || {};
        if (document.activeElement?.tagName !== 'INPUT') {
          $('geoMudWeight').value = p.mud_weight ?? 9;
          $('geoAzimuth').value = p.shmax_azimuth ?? 0;
          $('geoShminGrad').value = p.shmin_gradient ?? 0.7;
          $('geoShmaxGrad').value = p.shmax_gradient ?? 1.2;
        }
        $('geoFormNote').textContent = this.state.model.status === 'approved' ? 'Approved · create a new model to edit.' : 'Draft models are editable.';
      }
    },

    renderBadges() {
      const cal = this.state.model?.calibration || {};
      const set = (id, label, kind) => {
        const el = $(id);
        el.className = `px-badge ${kind}`;
        el.innerHTML = `<i class="px-badge-dot"></i>${esc(label)}`;
      };
      set('geoBadgePp', Array.isArray(cal.pp) && cal.pp.length >= 2 ? 'Pp calibrated' : 'Pp correlation', Array.isArray(cal.pp) && cal.pp.length >= 2 ? 'px-info' : 'px-warn');
      set('geoBadgeShmin', Array.isArray(cal.shmin) && cal.shmin.length >= 2 ? 'Shmin calibrated' : 'Shmin assumed', Array.isArray(cal.shmin) && cal.shmin.length >= 2 ? 'px-info' : 'px-warn');
      set('geoBadgeShmax', Array.isArray(cal.shmax) && cal.shmax.length >= 2 ? 'Shmax calibrated' : 'Shmax assumed', Array.isArray(cal.shmax) && cal.shmax.length >= 2 ? 'px-info' : 'px-warn');
    },

    renderEmpty() {
      this.state.result = null;
      $('geoProfileMeta').textContent = 'no model';
      $('geoProvMeta').textContent = 'draft';
      $('geoMudWindow').innerHTML = '— <span class="px-kpi-unit">ppg</span>';
      $('geoBreakouts').innerHTML = '— <span class="px-kpi-unit">intervals</span>';
      $('geoFailureRows').innerHTML = '<tr><td colspan="7" class="px-muted">Create a model and compute to populate failure intervals.</td></tr>';
      $('geoComputeState').textContent = 'No compute run yet.';
      $('geoWindowMeta').textContent = 'no computed interval';
      $('geoFailureMeta').textContent = '0 flagged';
      this.drawProfile(null);
    },

    async createModel() {
      try {
        const model = await app._api(`/wells/${this.state.wid}/geomechanics/models`, {
          method: 'POST',
          body: JSON.stringify({ params: this.params(), calibration: {}, model_type: 'screening' }),
        });
        this.state.selectedId = model.id;
        GeoToast.success(`Created model v${model.version}`);
        await this.load();
      } catch (e) { GeoToast.error(e.message); }
    },

    calibrateBreakouts() {
      const model = this.state.model;
      if (!model) return GeoToast.warn('Create a model first.');
      if (model.status === 'approved') return GeoToast.warn('Approved models are immutable.');
      PxModal.open({
        title: `Breakout calibration · model v${model.version}`,
        body: `<p>Enter one breakout per line: <code>depth, width_deg[, mud_weight]</code>. SHmax is inverted from the vertical-well Kirsch hoop stress at the breakout edge using the current Pp/Shmin and UCS.</p>
          <textarea id="geoBreakoutText" aria-label="Breakout rows" placeholder="1046.2, 30, 9.2\n1076.4, 24, 9.0"></textarea>
          <p>This estimates calibration points; review the values before operational use.</p>`,
        primaryLabel: 'Estimate & save',
        onPrimary: async () => {
          const lines = (document.getElementById('geoBreakoutText').value || '').split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
          const breakouts = [];
          for (const line of lines) {
            const parts = line.split(',').map((s) => Number(s.trim()));
            if (parts.length < 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1])) continue;
            const item = { depth: parts[0], width_deg: parts[1] };
            if (Number.isFinite(parts[2])) item.mud_weight = parts[2];
            breakouts.push(item);
          }
          if (!breakouts.length) return GeoToast.error('Add at least one valid breakout row.');
          try {
            const result = await app._api(`/wells/${this.state.wid}/geomechanics/breakout-calibration`, {
              method: 'POST', body: JSON.stringify({ model_id: model.id, breakouts, save: true }),
            });
            PxModal.close();
            GeoToast.success(`${result.points.length} SHmax points saved · avg ${num(result.average_shmax, 0)} psi`);
            await this.load();
          } catch (e) { GeoToast.error(e.message); }
        },
      });
    },

    editCalibration() {
      const model = this.state.model;
      if (!model) return GeoToast.warn('Create a model first.');
      if (model.status === 'approved') {
        PxModal.open({
          title: 'Calibration · approved model',
          body: '<p>This model is approved and immutable. Create a new model to change calibration.</p>',
          primaryLabel: '',
        });
        return;
      }
      const body = `<p>Calibration points are <code>[depth, value]</code> pairs in psi. Supported keys: <code>pp</code>, <code>shmin</code>, <code>shmax</code>, <code>shmax_azimuth</code>, and optional <code>fracture_planes</code>.</p>
        <textarea id="geoCalJson" aria-label="Calibration JSON">${esc(JSON.stringify(model.calibration || {}, null, 2))}</textarea>`;
      PxModal.open({
        title: `Calibration · model v${model.version}`,
        body,
        primaryLabel: 'Save calibration',
        onPrimary: async () => {
          let parsed;
          try { parsed = JSON.parse(document.getElementById('geoCalJson').value || '{}'); }
          catch (e) { return GeoToast.error(`Invalid JSON: ${e.message}`); }
          if (Array.isArray(parsed) || typeof parsed !== 'object' || parsed === null) return GeoToast.error('Calibration must be a JSON object.');
          try {
            await app._api(`/wells/${this.state.wid}/geomechanics/models/${model.id}`, {
              method: 'PUT', body: JSON.stringify({ calibration: parsed }),
            });
            PxModal.close();
            GeoToast.success('Calibration saved');
            await this.load();
          } catch (e) { GeoToast.error(e.message); }
        },
      });
    },

    async saveModel() {
      const model = this.state.model;
      if (!model) return this.createModel();
      if (model.status === 'approved') return GeoToast.warn('Approved models are immutable; create a new model.');
      try {
        await app._api(`/wells/${this.state.wid}/geomechanics/models/${model.id}`, {
          method: 'PUT', body: JSON.stringify({ params: this.params() }),
        });
        GeoToast.success('Model parameters saved');
        await this.load();
      } catch (e) { GeoToast.error(e.message); }
    },

    async compute(showToast = true) {
      if (this.state.busy) return;
      if (!this.state.model) return this.createModel();
      this.state.busy = true;
      this.setState('Computing screening model…');
      try {
        const result = await app._api(`/wells/${this.state.wid}/geomechanics/compute`, {
          method: 'POST', body: JSON.stringify({ model_id: this.state.model.id }),
        });
        this.state.result = result;
        this.renderResult(result);
        if (showToast) GeoToast.success(`Computed ${result.summary.points} depth samples`);
      } catch (e) {
        this.setState('Compute failed.');
        GeoToast.error(e.message);
      } finally {
        this.state.busy = false;
        $('geoRoot').classList.remove('px-loading');
      }
    },

    setState(text) {
      $('geoComputeState').textContent = text;
      $('geoRoot').classList.add('px-loading');
    },

    renderResult(result) {
      const s = result.summary, prov = result.provenance || {};
      $('geoProfileMeta').textContent = `${num(s.depth_top, 0)}–${num(s.depth_bottom, 0)} m MD`;
      $('geoProvMeta').textContent = `${this.state.model?.status || 'draft'} · v${this.state.model?.version || '—'}`;
      $('geoMudWindow').innerHTML = `${num(s.mw_min, 1)}–${num(s.mw_max, 1)} <span class="px-kpi-unit">ppg</span>`;
      $('geoBreakouts').innerHTML = `${s.breakout_count ?? 0} <span class="px-kpi-unit">intervals</span>`;
      $('geoComputeState').textContent = `Computed ${new Date().toLocaleTimeString()} · ${s.points} samples`;
      $('geoWindowMeta').textContent = `${num(s.depth_top, 0)}–${num(s.depth_bottom, 0)} m · criteria set 04`;
      this.renderProvenance(prov);
      this.renderCalibration();
      this.renderFailures(result);
      this.drawProfile(result);
    },

    renderProvenance(prov) {
      const labels = [
        ['Sv', 'Vertical stress · Sv', prov.SV],
        ['Pp', 'Pore pressure · Pp', prov.PP],
        ['Shmin', 'Min horizontal · Shmin', prov.SHMIN],
        ['Shmax', 'Max horizontal · Shmax', prov.SHMAX],
        ['E', 'Static Young’s modulus', prov.E],
        ['Nu', 'Poisson’s ratio', prov.NU],
      ];
      $('geoProvGrid').innerHTML = labels.map(([, label, value]) =>
        `<div class="px-prov-item"><span class="px-prov-label">${esc(label)}</span><span class="px-prov-value">${esc(value || 'not_available')} <span class="px-badge ${badgeClass(value)}">${esc(String(value || '—').toUpperCase())}</span></span></div>`
      ).join('');
    },

    renderCalibration() {
      const cal = this.state.model?.calibration || {};
      const rows = [];
      const add = (name, list) => (list || []).forEach((pt) => {
        const depth = Array.isArray(pt) ? pt[0] : pt.depth;
        const value = Array.isArray(pt) ? pt[1] : (pt.value ?? pt.pressure);
        rows.push({ name, depth, value });
      });
      add('Pp', cal.pp); add('Shmin', cal.shmin); add('Shmax', cal.shmax);
      $('geoCalCount').textContent = `${rows.length} point${rows.length === 1 ? '' : 's'}`;
      $('geoCalList').innerHTML = rows.length
        ? rows.map((r) => `<div class="px-cal-row"><span>${esc(r.name)} · ${num(r.depth, 1)} m</span><span class="px-data">${num(r.value, 0)}</span><span class="px-data">psi</span><span class="px-badge px-ok">FIT</span></div>`).join('')
        : '<div class="px-cal-row"><span>No calibration points</span><span class="px-data">—</span><span class="px-data">—</span><span class="px-badge">—</span></div>';
    },

    renderFailures(result) {
      const c = result.curves, n = c.DEPTH?.length || 0;
      const rows = [];
      let start = null;
      const flush = (end) => {
        if (start === null) return;
        const a = start, b = end;
        const slice = (arr) => arr ? arr.slice(a, b + 1) : [];
        const pct = (arr) => { const vals = slice(arr).filter((v) => v !== null); return vals.length ? Math.round(vals.filter(Boolean).length / vals.length * 100) : 0; };
        const max = (arr) => { const vals = slice(arr).filter((v) => v !== null); return vals.length ? Math.max(...vals) : 0; };
        const bo = pct(c.BO), mc = pct(c.MC_FAIL), hb = pct(c.HB_FAIL), dp = pct(c.DP_FAIL), sand = max(c.SAND_CDP);
        const risk = bo >= 50 ? 'px-high' : (bo > 0 || sand > 0 ? 'px-watch' : 'px-low');
        const label = bo >= 50 ? 'Review · BO' : sand > 0 ? 'Watch · sanding' : 'Watch';
        rows.push(`<tr><td>${num(c.DEPTH[a], 1)}–${num(c.DEPTH[b], 1)}</td><td>${bo}%</td><td>${mc}%</td><td>${hb}%</td><td>${dp}%</td><td>${num(sand, 1)}</td><td><span class="px-risk ${risk}">${label}</span></td></tr>`);
        start = null;
      };
      for (let i = 0; i < n; i++) {
        const flagged = c.BO[i] || c.MC_FAIL[i] || c.HB_FAIL[i] || c.DP_FAIL[i] || (c.SAND_CDP[i] > 0);
        if (flagged && start === null) start = i;
        if (!flagged && start !== null) flush(i - 1);
      }
      flush(n - 1);
      const shown = rows.slice(0, 6);
      $('geoFailureRows').innerHTML = shown.length ? shown.join('') : '<tr><td colspan="7" class="px-muted">No flagged intervals in this run.</td></tr>';
      $('geoFailureMeta').textContent = `${rows.length} flagged`;
      $('geoFailureMeta').style.color = rows.length ? 'var(--px-accent)' : 'var(--px-muted)';
    },

    drawProfile(result) {
      const canvas = $('geoProfile');
      if (!canvas || !canvas.clientWidth) return;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth, h = canvas.clientHeight || 420;
      canvas.width = w * dpr; canvas.height = h * dpr;
      const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      if (!result) {
        ctx.fillStyle = 'var(--px-muted)'; ctx.font = '11px Geologica'; ctx.textAlign = 'center';
        ctx.fillText('Create a model and compute to see the pressure profile.', w / 2, h / 2);
        return;
      }
      const c = result.curves, n = c.DEPTH.length;
      const pad = { l: 54, r: 14, t: 14, b: 36 };
      const depths = c.DEPTH.map(Number), tvd = c.TVD.map(Number);
      const d0 = Math.min(...depths), d1 = Math.max(...depths);
      const maxP = Math.max(...c.SV, ...c.SHMAX, ...c.MW_MAX.map((v) => (v ?? 0) * 0.052 * (tvd[0] || 1)), 1);
      const px = (p) => pad.l + (p / maxP) * (w - pad.l - pad.r);
      const py = (d) => pad.t + ((d - d0) / Math.max(1, d1 - d0)) * (h - pad.t - pad.b);
      ctx.strokeStyle = '#2a3446'; ctx.lineWidth = 1;
      for (let i = 0; i <= 5; i++) {
        const d = d0 + (d1 - d0) * i / 5;
        ctx.beginPath(); ctx.moveTo(pad.l, py(d)); ctx.lineTo(w - pad.r, py(d)); ctx.stroke();
        ctx.fillStyle = '#9aa8b8'; ctx.font = '9px JetBrains Mono'; ctx.textAlign = 'right'; ctx.fillText(Math.round(d).toLocaleString(), pad.l - 7, py(d) + 3);
      }
      for (let i = 0; i <= 6; i++) {
        const p = maxP * i / 6;
        ctx.beginPath(); ctx.moveTo(px(p), pad.t); ctx.lineTo(px(p), h - pad.b); ctx.stroke();
        ctx.fillStyle = '#9aa8b8'; ctx.textAlign = 'center'; ctx.fillText(Math.round(p).toLocaleString(), px(p), h - 20);
      }
      ctx.fillStyle = '#9aa8b8'; ctx.textAlign = 'center'; ctx.fillText('Pressure (psi)', (pad.l + w - pad.r) / 2, h - 2);
      ctx.save(); ctx.translate(13, h / 2); ctx.rotate(-Math.PI / 2); ctx.fillText('Measured depth (m)', 0, 0); ctx.restore();

      const band = [];
      for (let i = 0; i < n; i++) {
        if (c.MW_MIN[i] == null || c.MW_MAX[i] == null) continue;
        band.push([px((c.MW_MIN[i] || 0) * 0.052 * (tvd[i] || 0)), py(depths[i]), px((c.MW_MAX[i] || 0) * 0.052 * (tvd[i] || 0)), py(depths[i])]);
      }
      if (band.length) {
        ctx.beginPath();
        band.forEach((b, i) => i ? ctx.lineTo(b[0], b[1]) : ctx.moveTo(b[0], b[1]));
        [...band].reverse().forEach((b) => ctx.lineTo(b[2], b[3]));
        ctx.closePath(); ctx.fillStyle = 'rgba(212,168,83,.12)'; ctx.fill();
      }
      const line = (arr, color, width = 2) => {
        ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = width;
        let started = false;
        for (let i = 0; i < n; i++) {
          const v = Number(arr[i]);
          if (!Number.isFinite(v)) { started = false; continue; }
          const X = px(v), Y = py(depths[i]);
          started ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); started = true;
        }
        ctx.stroke();
      };
      line(c.SV, '#d9e0df', 2.1);
      line(c.PP, '#5ba8a0', 2.2);
      line(c.SHMIN, '#d4a853', 2.2);
      line(c.SHMAX, '#91a4d0', 2.2);
      const cal = this.state.model?.calibration || {};
      const plotPts = (list, color) => (list || []).forEach((pt) => {
        const depth = Array.isArray(pt) ? pt[0] : pt.depth;
        const value = Array.isArray(pt) ? pt[1] : (pt.value ?? pt.pressure);
        if (!Number.isFinite(Number(depth)) || !Number.isFinite(Number(value))) return;
        ctx.beginPath(); ctx.fillStyle = color; ctx.strokeStyle = '#0a0e14'; ctx.lineWidth = 2;
        ctx.arc(px(Number(value)), py(Number(depth)), 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      });
      plotPts(cal.pp, '#5ba8a0'); plotPts(cal.shmin, '#d4a853'); plotPts(cal.shmax, '#91a4d0');
    },

    async exportPdf() {
      if (!this.state.model) return GeoToast.warn('Create a model first.');
      try {
        const blob = await app._apiBlob(`/wells/${this.state.wid}/geomechanics/report?model_id=${this.state.model.id}&format=pdf`);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `geomechanics_${this.state.wid}.pdf`; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
      } catch (e) { GeoToast.error(e.message); }
    },
  };

  window.GeomechanicsView = View;
  document.addEventListener('DOMContentLoaded', () => {
    const redraw = () => {
      if ($('geomechanicsPanel')?.style.display === 'none') return;
      View.drawProfile(View.state.result);
    };
    if (window.ResizeObserver) new ResizeObserver(redraw).observe($('geomechanicsPanel'));
    window.addEventListener('resize', redraw);
    $('geoModel')?.addEventListener('change', async (e) => {
      View.state.selectedId = Number(e.target.value) || null;
      View.state.model = View.state.models.find((m) => m.id === View.state.selectedId) || null;
      View.renderBadges();
      if (View.state.model) await View.compute(false); else View.renderEmpty();
    });
    $('geoNewBtn')?.addEventListener('click', () => View.createModel());
    $('geoSaveBtn')?.addEventListener('click', () => View.saveModel());
    $('geoCalBtn')?.addEventListener('click', () => View.editCalibration());
    $('geoBreakoutBtn')?.addEventListener('click', () => View.calibrateBreakouts());
    $('geoComputeBtn')?.addEventListener('click', () => View.compute());
    $('geoExportBtn')?.addEventListener('click', () => View.exportPdf());
  });
})();
