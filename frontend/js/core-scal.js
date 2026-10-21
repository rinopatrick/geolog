/* Core / SCAL workbench. Data comes from /api/wells/{id}/core*.
   Layout follows the OpenDesign "tech-utility" direction; charts are canvas. */
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (v, d = 1) => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d);
  const fzi = (p) => {
    const phi = Number(p.porosity), k = Number(p.perm_air);
    if (!(phi > 0 && phi < 1) || !(k > 0)) return null;
    return 0.0314 * Math.sqrt(k / phi) / (phi / (1 - phi));
  };

  const View = {
    state: { wid: null, datasets: [], plugs: [], rocks: [], units: [], models: [], selectedId: null, datasetId: null, source: '', shModelId: null, shResult: null, pcMode: 'pc', pendingImport: null },

    async load() {
      if (!app.currentWell) return;
      this.state.wid = app.currentWell.id;
      try {
        const base = `/wells/${this.state.wid}`;
        const [datasets, plugs, rocks, units, models] = await Promise.all([
          app._api(`${base}/core/datasets`),
          app._api(`${base}/core/plugs`),
          app._api(`${base}/core/rock-types`),
          app._api(`${base}/core/flow-units`),
          app._api(`${base}/core/saturation-height/models`),
        ]);
        Object.assign(this.state, { datasets, plugs, rocks, units, models });
        if (this.state.selectedId && !plugs.some((p) => p.id === this.state.selectedId)) this.state.selectedId = null;
        if (!this.state.selectedId && plugs.length) this.state.selectedId = plugs[0].id;
        this.render();
        this.renderShModels();
        this.selectPlug(this.state.selectedId, true);
      } catch (e) {
        GeoToast.error(`Core data: ${e.message}`);
      }
    },

    filteredPlugs() {
      return this.state.plugs.filter((p) => {
        if (this.state.datasetId && p.dataset_id !== this.state.datasetId) return false;
        if (this.state.source && (p.source || '') !== this.state.source) return false;
        return true;
      });
    },

    render() {
      const s = this.state;
      const plugs = this.filteredPlugs();
      const ds = s.datasets.find((d) => d.id === s.datasetId) || s.datasets[0];
      const datasetSelect = $('csDataset');
      datasetSelect.innerHTML = (s.datasets.length ? s.datasets : [{ id: '', version: '—', status: 'none' }])
        .map((d) => `<option value="${d.id}" ${d.id === (s.datasetId || ds?.id) ? 'selected' : ''}>Core v${esc(d.version)} · ${esc(d.status)}</option>`).join('');
      if (s.datasetId === null && ds) s.datasetId = ds.id;

      const sources = [...new Set(s.plugs.map((p) => p.source).filter(Boolean))].sort();
      $('csSource').innerHTML = '<option value="">All core data</option>' + sources.map((x) => `<option ${x === s.source ? 'selected' : ''}>${esc(x)}</option>`).join('');

      const phis = plugs.map((p) => Number(p.porosity) * 100).filter((v) => Number.isFinite(v) && v > 0);
      const perms = plugs.map((p) => Number(p.perm_air)).filter((v) => Number.isFinite(v) && v > 0);
      const latestVersion = s.units.length ? Math.max(...s.units.map((u) => u.version)) : 0;
      const clusters = s.units.filter((u) => u.version === latestVersion).length;
      const approvedIds = new Set(s.datasets.filter((d) => d.status === 'approved').map((d) => d.id));
      const approved = plugs.length ? Math.round(plugs.filter((p) => approvedIds.has(p.dataset_id)).length / plugs.length * 100) : 0;

      $('csKpiPlugs').textContent = plugs.length;
      $('csKpiPhi').textContent = phis.length ? `${num(Math.min(...phis))}–${num(Math.max(...phis))}` : '—';
      $('csKpiPerm').textContent = perms.length ? `${num(Math.min(...perms), 0)}–${num(Math.max(...perms), 0)}` : '—';
      $('csKpiFzi').textContent = clusters;
      $('csKpiApproved').textContent = approved;

      const status = $('csDatasetStatus');
      if (ds && ds.status === 'approved') {
        status.className = 'px-badge px-ok';
        status.innerHTML = `<i class="px-badge-dot"></i>Approved · v${esc(ds.version)}`;
        $('csApproveBtn').disabled = true;
      } else if (ds) {
        status.className = 'px-badge px-warn';
        status.innerHTML = `<i class="px-badge-dot"></i>Draft · not approved`;
        $('csApproveBtn').disabled = false;
      } else {
        status.className = 'px-badge';
        status.innerHTML = '<i class="px-badge-dot"></i>No dataset';
        $('csApproveBtn').disabled = true;
      }

      const rocks = new Map(s.rocks.map((r) => [r.id, r.name]));
      const rows = plugs.map((p) => {
        const f = fzi(p);
        const r = p.rock_type_id ? rocks.get(p.rock_type_id) : '';
        const review = !(Number(p.porosity) > 0) || !(Number(p.perm_air) > 0) || !r;
        return `<tr class="px-plug-row" tabindex="0" aria-selected="${p.id === s.selectedId}" data-id="${p.id}">
          <td class="px-plug-id">${esc(p.plug_name)}</td><td>${num(p.depth_md, 1)}</td><td>${esc(p.formation || '—')}</td>
          <td>${num(Number(p.porosity) * 100, 1)}</td><td>${num(p.perm_air, 0)}</td><td>${f === null ? '—' : num(f, 1)}</td>
          <td class="px-rock">${esc(r || 'Unassigned')}</td>
          <td><span class="px-qc ${review ? 'px-review' : 'px-pass'}" title="${review ? 'Review required' : 'QC passed'}">${review ? '!' : '✓'}</span></td></tr>`;
      }).join('');
      $('csPlugRows').innerHTML = rows;
      $('csEmpty').hidden = plugs.length > 0;
      $('csTableCount').textContent = `${plugs.length} measurement${plugs.length === 1 ? '' : 's'}`;
      $('csQcCount').textContent = `${plugs.filter((p) => !(Number(p.porosity) > 0) || !(Number(p.perm_air) > 0) || !(p.rock_type_id)).length} QC REVIEW`;
      $('csPlugRows').querySelectorAll('.px-plug-row').forEach((row) => {
        const pick = () => this.selectPlug(Number(row.dataset.id));
        row.addEventListener('click', pick);
        row.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
      });
      this.drawCrossplot(plugs);
    },

    renderShModels() {
      const select = $('csShModel');
      if (!select) return;
      const models = this.state.models || [];
      if (!models.length) { select.innerHTML = '<option value="">No SH model</option>'; return; }
      if (!models.some((m) => m.id === this.state.shModelId)) this.state.shModelId = models[0].id;
      select.innerHTML = models.map((m) => `<option value="${m.id}" ${m.id === this.state.shModelId ? 'selected' : ''}>SH v${esc(m.version)} · ${esc(m.model_type)} · R² ${num(m.r2, 2)}</option>`).join('');
    },

    async applySh() {
      if (!this.state.shModelId) return GeoToast.warn('Fit a saturation-height model first.');
      try {
        const result = await app._api(`/wells/${this.state.wid}/core/saturation-height/apply`, {
          method: 'POST', body: JSON.stringify({ model_id: this.state.shModelId }),
        });
        this.state.shResult = result;
        this.state.pcMode = 'sh';
        $('csPcToggle').hidden = false;
        $('csPcToggle').textContent = 'Show Pc';
        $('csPcMethod').textContent = 'SH';
        const target = Number(result.contact_depth) - 100;
        let best = null;
        (result.depth || []).forEach((d, i) => {
          if (result.sw[i] == null) return;
          if (!best || Math.abs(Number(d) - target) < Math.abs(Number(best.d) - target)) best = { d: Number(d), sw: Number(result.sw[i]) };
        });
        if (best) $('csSummarySw').textContent = `${(best.sw * 100).toFixed(1)} %`;
        GeoToast.success(`SH applied to ${result.sw.length} samples`);
        this.drawPc([]);
      } catch (e) { GeoToast.error(e.message); }
    },

    togglePc() {
      this.state.pcMode = this.state.pcMode === 'sh' ? 'pc' : 'sh';
      $('csPcMethod').textContent = this.state.pcMode === 'sh' ? 'SH' : 'Pc';
      $('csPcToggle').textContent = this.state.pcMode === 'sh' ? 'Show Pc' : 'Show SH';
      const plug = this.state.plugs.find((p) => p.id === this.state.selectedId);
      this.drawPc(plug?.pc_rows || []);
    },

    async selectPlug(id, draw = true) {
      if (!id) return;
      this.state.selectedId = id;
      document.querySelectorAll('#csPlugRows .px-plug-row').forEach((r) => r.setAttribute('aria-selected', String(Number(r.dataset.id) === id)));
      let plug = this.state.plugs.find((p) => p.id === id);
      if (!plug) return;
      try {
        if (!plug.pc_rows) plug = await app._api(`/wells/${this.state.wid}/core/plugs/${id}`);
        this.state.plugs = this.state.plugs.map((p) => p.id === id ? { ...p, ...plug } : p);
      } catch (_) {}
      const phi = Number(plug.porosity) * 100;
      const k = Number(plug.perm_air);
      $('csSummaryPlug').textContent = plug.plug_name;
      $('csSummaryFormation').textContent = `${plug.formation || '—'} · ${num(plug.depth_md, 1)} m MD`;
      const latest = this.state.models[0];
      $('csSummaryR2').textContent = latest?.r2 != null ? num(latest.r2, 3) : '—';
      $('csSummarySw').textContent = '—';
      const f = fzi(plug);
      const ver = this.state.units.length ? Math.max(...this.state.units.map((u) => u.version)) : 0;
      const unit = this.state.units.find((u) => u.version === ver && f >= u.fzi_min && f <= u.fzi_max);
      $('csSummaryFlow').textContent = unit ? `FU-${unit.cluster_index + 1}` : '—';
      const approved = plug.pc_rows && plug.pc_rows.length > 0;
      $('csSummaryQc').innerHTML = approved ? '<span class="px-badge px-ok"><i class="px-badge-dot"></i>Fit accepted</span>' : '<span class="px-badge px-warn"><i class="px-badge-dot"></i>Pc review</span>';
      if (draw) this.drawPc(plug.pc_rows || []);
    },

    drawCrossplot(plugs) {
      const canvas = $('csCrossplot');
      if (!canvas || !canvas.clientWidth) return;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth, h = canvas.clientHeight || 260;
      canvas.width = w * dpr; canvas.height = h * dpr;
      const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const pad = { l: 48, r: 12, t: 14, b: 30 };
      const pts = plugs.map((p) => ({ phi: Number(p.porosity) * 100, k: Number(p.perm_air) }))
        .filter((p) => p.phi > 0 && p.k > 0);
      const x0 = 10, x1 = 34, y0 = 1, y1 = 10000;
      const px = (v) => pad.l + (v - x0) / (x1 - x0) * (w - pad.l - pad.r);
      const py = (v) => h - pad.b - (Math.log10(Math.min(y1, Math.max(y0, v))) - Math.log10(y0)) / (Math.log10(y1) - Math.log10(y0)) * (h - pad.t - pad.b);
      ctx.strokeStyle = '#2a3446'; ctx.lineWidth = 1;
      for (const p of [10, 14, 18, 22, 26, 30, 34]) { ctx.beginPath(); ctx.moveTo(px(p), pad.t); ctx.lineTo(px(p), h - pad.b); ctx.stroke(); ctx.fillStyle = '#9aa8b8'; ctx.font = '9px JetBrains Mono'; ctx.textAlign = 'center'; ctx.fillText(String(p), px(p), h - 12); }
      for (const k of [1, 10, 100, 1000, 10000]) { ctx.beginPath(); ctx.moveTo(pad.l, py(k)); ctx.lineTo(w - pad.r, py(k)); ctx.stroke(); ctx.fillStyle = '#9aa8b8'; ctx.textAlign = 'right'; ctx.fillText(k >= 1000 ? `${k / 1000}k` : String(k), pad.l - 6, py(k) + 3); }
      ctx.fillStyle = '#9aa8b8'; ctx.textAlign = 'center'; ctx.fillText('Porosity (%)', w / 2, h - 1);
      ctx.save(); ctx.translate(12, h / 2); ctx.rotate(-Math.PI / 2); ctx.fillText('Kair (mD)', 0, 0); ctx.restore();
      const colors = ['#5ba8a0', '#d4a853', '#91a4d0'];
      [2, 3.5, 5].forEach((f, i) => {
        ctx.strokeStyle = colors[i]; ctx.setLineDash([5, 4]); ctx.beginPath();
        for (let phi = x0; phi <= x1; phi += 1) {
          const k = Math.pow(f * (phi / 100) / (1 - phi / 100) / 0.0314, 2) * (phi / 100);
          if (k > 0 && k <= y1) { const X = px(phi), Y = py(k); if (phi === x0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y); }
        }
        ctx.stroke();
      });
      ctx.setLineDash([]);
      pts.forEach((p) => { ctx.fillStyle = '#d4a853'; ctx.strokeStyle = '#111720'; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(px(p.phi), py(p.k), 3.4, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); });
    },

    drawShProfile(result) {
      const canvas = $('csPcPlot');
      if (!canvas || !canvas.clientWidth) return;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth, h = canvas.clientHeight || 150;
      canvas.width = w * dpr; canvas.height = h * dpr;
      const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const depths = result.depth.map(Number), sw = result.sw.map(Number);
      const valid = depths.map((d, i) => [d, sw[i]]).filter(([, v]) => Number.isFinite(v));
      $('csPcHead').textContent = `SH profile · ${result.contact_depth} m contact`;
      if (!valid.length) { ctx.fillStyle = '#6b7a8d'; ctx.font = '10px Geologica'; ctx.textAlign = 'center'; ctx.fillText('No valid SH samples', w / 2, h / 2); return; }
      const pad = { l: 46, r: 12, t: 12, b: 26 };
      const d0 = Math.min(...valid.map((p) => p[0])), d1 = Math.max(...valid.map((p) => p[0]));
      const px = (v) => pad.l + (1 - v) * (w - pad.l - pad.r);
      const py = (d) => pad.t + ((d - d0) / Math.max(1e-9, d1 - d0)) * (h - pad.t - pad.b);
      ctx.strokeStyle = '#2a3446'; ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {
        const v = i / 4;
        ctx.beginPath(); ctx.moveTo(px(v), pad.t); ctx.lineTo(px(v), h - pad.b); ctx.stroke();
        ctx.fillStyle = '#9aa8b8'; ctx.font = '9px JetBrains Mono'; ctx.textAlign = 'center'; ctx.fillText(`${Math.round(v * 100)}`, px(v), h - 10);
      }
      for (let i = 0; i <= 3; i++) {
        const d = d0 + (d1 - d0) * i / 3;
        ctx.beginPath(); ctx.moveTo(pad.l, py(d)); ctx.lineTo(w - pad.r, py(d)); ctx.stroke();
        ctx.fillStyle = '#9aa8b8'; ctx.textAlign = 'right'; ctx.fillText(d.toFixed(0), pad.l - 5, py(d) + 3);
      }
      ctx.beginPath();
      valid.forEach(([d, v], i) => { const X = px(v), Y = py(d); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); });
      ctx.strokeStyle = '#d4a853'; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = '#9aa8b8'; ctx.textAlign = 'center'; ctx.fillText('Sw (fraction)', w / 2, h - 1);
    },

    drawPc(rows) {
      const canvas = $('csPcPlot');
      if (this.state.pcMode === 'sh' && this.state.shResult) {
        this.drawShProfile(this.state.shResult);
        return;
      }
      if (!canvas || !canvas.clientWidth) return;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth, h = canvas.clientHeight || 150;
      canvas.width = w * dpr; canvas.height = h * dpr;
      const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const row = rows[0];
      const points = row?.points || [];
      $('csPcHead').textContent = points.length ? `plug ${this.state.selectedId} · ${row.test_type || 'drainage'}` : 'no Pc data';
      if (!points.length) { ctx.fillStyle = '#6b7a8d'; ctx.font = '10px Geologica'; ctx.textAlign = 'center'; ctx.fillText('No capillary pressure measurements', w / 2, h / 2); return; }
      const pad = { l: 42, r: 12, t: 12, b: 26 };
      const maxPc = Math.max(...points.map((p) => Number(p[0]))) || 1;
      const px = (sw) => pad.l + (1 - sw) * (w - pad.l - pad.r);
      const py = (pc) => h - pad.b - (pc / maxPc) * (h - pad.t - pad.b);
      ctx.strokeStyle = '#2a3446'; ctx.lineWidth = 1;
      for (let i = 0; i <= 3; i++) { const y = pad.t + i * (h - pad.t - pad.b) / 3; ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke(); ctx.fillStyle = '#9aa8b8'; ctx.font = '9px JetBrains Mono'; ctx.textAlign = 'right'; ctx.fillText(Math.round(maxPc * (1 - i / 3)), pad.l - 5, y + 3); }
      ctx.beginPath(); points.forEach((p, i) => { const X = px(Number(p[1])), Y = py(Number(p[0])); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }); ctx.strokeStyle = '#5ba8a0'; ctx.lineWidth = 2; ctx.stroke();
      points.forEach((p) => { ctx.fillStyle = '#5ba8a0'; ctx.beginPath(); ctx.arc(px(Number(p[1])), py(Number(p[0])), 2.6, 0, Math.PI * 2); ctx.fill(); });
      ctx.fillStyle = '#9aa8b8'; ctx.textAlign = 'center'; ctx.fillText('Sw (%)', w / 2, h - 1);
    },

    async approve() {
      const id = this.state.datasetId || this.state.datasets[0]?.id;
      if (!id) return;
      try { await app._api(`/wells/${this.state.wid}/core/datasets/${id}/approve`, { method: 'POST' }); GeoToast.success('Core dataset approved'); await this.load(); }
      catch (e) { GeoToast.error(e.message); }
    },

    async cluster() {
      try { const r = await app._api(`/wells/${this.state.wid}/core/flow-units/cluster`, { method: 'POST', body: JSON.stringify({ k: 3 }) }); GeoToast.success(`Flow units v${r.version}: ${r.k} clusters`); await this.load(); }
      catch (e) { GeoToast.error(e.message); }
    },

    async fitSh() {
      try { const r = await app._api(`/wells/${this.state.wid}/core/saturation-height/fit`, { method: 'POST', body: JSON.stringify({ model_type: $('csShFitType').value || 'j_function' }) }); GeoToast.success(`J-function fit R² ${num(r.r2, 3)}`); await this.load(); }
      catch (e) { GeoToast.error(e.message); }
    },

    matchDepth() {
      const plug = this.state.plugs.find((p) => p.id === this.state.selectedId);
      const lr = app.currentLogRun || app.currentWell?.log_runs?.[0];
      if (!plug) return GeoToast.warn('Select a core plug first.');
      if (!lr) return GeoToast.warn('Select a log run first.');
      PxModal.open({
        title: `Depth match · ${plug.plug_name}`,
        body: `<p>Core MD <strong>${num(plug.depth_md, 3)}</strong> · log run <strong>${esc(lr.filename || lr.id)}</strong></p>
          <label style="display:block;color:var(--px-muted);font-size:9px;margin-top:8px">Shift (positive = deeper log match)
            <input id="csMatchShift" class="px-text-control" type="number" step="0.1" value="0" style="width:100%;margin-top:4px">
          </label>
          <p style="margin-top:8px">Stages a proposed match and applies it immediately. Approved datasets are immutable.</p>`,
        primaryLabel: 'Stage & apply',
        onPrimary: async () => {
          const shift = Number(document.getElementById('csMatchShift').value || 0);
          try {
            const match = await app._api(`/wells/${this.state.wid}/core/plugs/${plug.id}/depth-match`, {
              method: 'POST', body: JSON.stringify({ log_run_id: lr.id, shift }),
            });
            await app._api(`/wells/${this.state.wid}/core/depth-matches/${match.id}/apply`, { method: 'POST' });
            PxModal.close();
            GeoToast.success(`Matched ${plug.plug_name} to ${num(match.log_md, 3)} MD`);
            await this.load();
          } catch (e) { GeoToast.error(e.message); }
        },
      });
    },

    async previewImport(file) {
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file);
      try {
        const resp = await fetch(`/api/wells/${this.state.wid}/core/import?dry_run=true`, {
          method: 'POST', headers: app._authHeaders(), body: fd,
        });
        const report = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(report.detail || `Preview failed (${resp.status})`);
        this.state.pendingImport = { file, report };
        const conflicts = (report.conflicts || []).slice(0, 10);
        const errors = (report.errors || []).slice(0, 10);
        const rows = (items, kind) => items.length
          ? `<table><thead><tr><th>Line</th><th>${kind === 'conflict' ? 'Plug' : 'Error'}</th><th>MD</th></tr></thead><tbody>${items.map((x) => `<tr><td>${esc(x.line)}</td><td>${esc(kind === 'conflict' ? x.plug_name : x.error)}</td><td>${kind === 'conflict' ? num(x.depth_md, 2) : '—'}</td></tr>`).join('')}</tbody></table>`
          : '<p>None.</p>';
        const body = `
          <div class="px-import-summary">
            <div class="px-import-stat"><span>DATA ROWS</span><strong>${report.rows ?? 0}</strong></div>
            <div class="px-import-stat"><span>WOULD IMPORT</span><strong>${report.would_import ?? 0}</strong></div>
            <div class="px-import-stat"><span>CONFLICTS</span><strong>${(report.conflicts || []).length}</strong></div>
            <div class="px-import-stat"><span>ERRORS</span><strong>${(report.errors || []).length}</strong></div>
          </div>
          <p><strong>${esc(file.name)}</strong> · dry run only, nothing has been written yet.</p>
          <h3 style="font-size:10px;margin:12px 0 5px;color:var(--px-muted)">CONFLICTS</h3>${rows(conflicts, 'conflict')}
          <h3 style="font-size:10px;margin:12px 0 5px;color:var(--px-muted)">ERRORS</h3>${rows(errors, 'error')}
          <p style="margin-top:12px">Conflicts are existing <code>(plug_name, depth_md)</code> keys. Import new skips them; update existing overwrites the plug fields.</p>`;
        PxModal.open({
          title: 'Core CSV import preview',
          body,
          primaryLabel: report.would_import ? 'Import new' : '',
          secondaryLabel: (report.conflicts || []).length ? 'Update existing' : '',
          onPrimary: () => this.confirmImport(false),
          onSecondary: () => this.confirmImport(true),
        });
      } catch (e) { GeoToast.error(e.message); }
    },

    async confirmImport(update) {
      const pending = this.state.pendingImport;
      if (!pending) return;
      const fd = new FormData();
      fd.append('file', pending.file);
      try {
        const resp = await fetch(`/api/wells/${this.state.wid}/core/import${update ? '?update=true' : ''}`, {
          method: 'POST', headers: app._authHeaders(), body: fd,
        });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(body.detail || `Import failed (${resp.status})`);
        PxModal.close();
        GeoToast.success(`Imported ${body.imported} plugs${body.conflicts?.length ? `, ${body.conflicts.length} skipped` : ''}`);
        this.state.pendingImport = null;
        await this.load();
      } catch (e) { GeoToast.error(e.message); }
    }
  };

  window.CoreScalView = View;
  document.addEventListener('DOMContentLoaded', () => {
    const redraw = () => {
      if ($('corescalPanel')?.style.display === 'none') return;
      View.drawCrossplot(View.filteredPlugs());
      const plug = View.state.plugs.find((p) => p.id === View.state.selectedId);
      if (plug) View.drawPc(plug.pc_rows || []);
    };
    if (window.ResizeObserver) new ResizeObserver(redraw).observe($('corescalPanel'));
    window.addEventListener('resize', redraw);
    $('csDataset')?.addEventListener('change', (e) => { View.state.datasetId = Number(e.target.value) || null; View.render(); View.selectPlug(View.filteredPlugs()[0]?.id); });
    $('csSource')?.addEventListener('change', (e) => { View.state.source = e.target.value; View.render(); });
    $('csApproveBtn')?.addEventListener('click', () => View.approve());
    $('csClusterBtn')?.addEventListener('click', () => View.cluster());
    $('csFitShBtn')?.addEventListener('click', () => View.fitSh());
    $('csImportBtn')?.addEventListener('click', () => $('csCsvFile').click());
    $('csCsvFile')?.addEventListener('change', (e) => View.previewImport(e.target.files?.[0]));
    $('csMatchBtn')?.addEventListener('click', () => View.matchDepth());
    $('csShModel')?.addEventListener('change', (e) => { View.state.shModelId = Number(e.target.value) || null; });
    $('csApplyShBtn')?.addEventListener('click', () => View.applySh());
    $('csPcToggle')?.addEventListener('click', () => View.togglePc());
  });
})();
