/* Image log asset viewer + manual dip trace fitting.
   Uses /api/wells/{id}/image-assets; the old synthetic /image-log endpoint is not used. */
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (v, d = 1) => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(d);
  const MAX_W = 256, MAX_H = 520;

  const View = {
    state: { wid: null, assets: [], selectedId: null, asset: null, trace: [], selectedPick: null, imageUrl: null },

    async load() {
      if (!app.currentWell) return;
      this.state.wid = app.currentWell.id;
      try {
        const assets = await app._api(`/wells/${this.state.wid}/image-assets`);
        this.state.assets = assets;
        if (this.state.selectedId && !assets.some((a) => a.id === this.state.selectedId)) this.state.selectedId = null;
        if (!this.state.selectedId && assets.length) this.state.selectedId = assets[0].id;
        this.renderAssetSelect();
        if (this.state.selectedId) await this.selectAsset(this.state.selectedId);
        else this.renderNoAsset();
      } catch (e) { GeoToast.error(`Image log: ${e.message}`); }
    },

    renderAssetSelect() {
      const select = $('imgAsset');
      select.innerHTML = this.state.assets.length
        ? this.state.assets.map((a) => `<option value="${a.id}" ${a.id === this.state.selectedId ? 'selected' : ''}>${esc(a.image_type || 'image')} · ${num(a.depth_top, 1)}–${num(a.depth_bottom, 1)} m</option>`).join('')
        : '<option value="">No image assets</option>';
    },

    renderNoAsset() {
      this.state.asset = null;
      $('imgEmpty').hidden = false;
      $('imgCaption').textContent = 'no asset';
      $('imgDepthRange').value = '—';
      $('imgRadius').value = '—';
      $('imgPickCount').textContent = '0 FEATURES';
      $('imgPickRows').innerHTML = '';
      $('imgApprovalCount').textContent = '0 picks';
      $('imgDepthAxis').innerHTML = '<span>—</span><span>—</span><span>—</span><span>—</span><span>—</span><span>—</span>';
      this.clearCanvas();
      this.renderVectorLayer();
      this.updateDetail(null);
    },

    clearCanvas() {
      const canvas = $('imgCanvas');
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#0a0e14'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    },

    async selectAsset(id) {
      if (!id) return this.renderNoAsset();
      this.state.selectedId = id;
      try {
        const asset = await app._api(`/wells/${this.state.wid}/image-assets/${id}`);
        this.state.asset = asset;
        this.state.trace = [];
        this.state.selectedPick = asset.dip_rows?.[0]?.id || null;
        $('imgEmpty').hidden = true;
        $('imgCaption').textContent = `${asset.width || '—'} × ${asset.height || '—'} px · ${asset.image_type || 'image'}`;
        $('imgDepthRange').value = `${num(asset.depth_top, 1)}–${num(asset.depth_bottom, 1)} m`;
        $('imgRadius').value = asset.borehole_radius != null ? `${num(asset.borehole_radius, 3)} m` : 'not set';
        $('imgMetaNote').textContent = asset.source || asset.image_type || 'PNG';
        $('imgDepthTop').value = asset.depth_top ?? '';
        $('imgDepthBottom').value = asset.depth_bottom ?? '';
        $('imgUploadRadius').value = asset.borehole_radius ?? 0.15;
        this.renderDepthAxis(asset);
        await this.loadImage(asset);
        this.renderPicks();
        this.renderVectorLayer();
        this.updateDetail(this.state.selectedPick);
        $('imgPickHint').textContent = 'Click the image to add trace points';
        $('imgScaleNote').textContent = 'Amplitude · normalized';
      } catch (e) { GeoToast.error(`Image asset: ${e.message}`); }
    },

    async loadImage(asset) {
      try {
        if (this.state.imageUrl) URL.revokeObjectURL(this.state.imageUrl);
        const blob = await app._apiBlob(`/wells/${this.state.wid}/image-assets/${asset.id}/file`);
        this.state.imageUrl = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
          const canvas = $('imgCanvas');
          const ctx = canvas.getContext('2d');
          ctx.fillStyle = '#0a0e14'; ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        };
        img.src = this.state.imageUrl;
      } catch (e) {
        this.clearCanvas();
        GeoToast.error(`Image file: ${e.message}`);
      }
    },

    renderDepthAxis(asset) {
      const top = Number(asset.depth_top), bottom = Number(asset.depth_bottom);
      const span = bottom - top || 1;
      const marks = [0, .2, .4, .6, .8, 1];
      $('imgDepthAxis').innerHTML = marks.map((f) => `<span>${num(top + span * f, 1)}</span>`).join('');
    },

    renderPicks() {
      const rows = this.state.asset?.dip_rows || [];
      $('imgPickCount').textContent = `${rows.length} FEATURE${rows.length === 1 ? '' : 'S'}`;
      $('imgPickRows').innerHTML = rows.length ? rows.map((r) => {
        const quality = r.r2 != null && r.r2 >= 0.8 ? 'Good' : 'Fair';
        return `<tr class="px-pick-row" tabindex="0" aria-selected="${r.id === this.state.selectedPick}" data-id="${r.id}">
          <td>${num(r.depth, 1)}</td><td>${num(r.dip_angle, 1)}</td><td>${num(r.dip_azimuth, 0)}</td><td>${num(r.r2, 2)}</td>
          <td><span class="px-quality ${quality === 'Fair' ? 'px-fair' : ''}">${quality}</span></td>
          <td><input class="px-pick-approved" type="checkbox" ${r.approved ? 'checked' : ''} aria-label="Approve pick at ${num(r.depth, 1)} metres"></td></tr>`;
      }).join('') : '<tr><td colspan="6" class="px-muted">No dip picks. Click the image and fit a trace.</td></tr>';
      const approved = rows.filter((r) => r.approved).length;
      $('imgApprovalCount').textContent = `${approved} of ${rows.length} picks approved`;
      $('imgPickRows').querySelectorAll('.px-pick-row').forEach((row) => {
        const pick = () => { this.state.selectedPick = Number(row.dataset.id); this.renderPicks(); this.renderVectorLayer(); this.updateDetail(this.state.selectedPick); };
        row.addEventListener('click', (e) => { if (e.target.closest('input')) return; pick(); });
        row.addEventListener('keydown', (e) => { if (!e.target.closest('input') && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pick(); } });
        row.querySelector('input')?.addEventListener('change', (e) => this.approveOne(Number(row.dataset.id), e.target));
      });
    },

    updateDetail(id) {
      const pick = (this.state.asset?.dip_rows || []).find((r) => r.id === id);
      if (!pick) {
        $('imgDetailDepth').textContent = '—'; $('imgDetailDip').textContent = '—'; $('imgDetailAz').textContent = '—';
        $('imgDetailR2').textContent = '—'; $('imgDetailQuality').textContent = '—'; $('imgDetailBy').textContent = '—';
        $('imgOrientationLine').setAttribute('d', 'M56 56 L56 56'); $('imgOrientationDot').setAttribute('cx', 56); $('imgOrientationDot').setAttribute('cy', 56);
        return;
      }
      $('imgDetailDepth').textContent = `${num(pick.depth, 1)} m`;
      $('imgDetailDip').textContent = `${num(pick.dip_angle, 1)}°`;
      $('imgDetailAz').textContent = `${num(pick.dip_azimuth, 0)}°`;
      $('imgDetailR2').textContent = num(pick.r2, 2);
      $('imgDetailQuality').textContent = pick.r2 != null && pick.r2 >= 0.8 ? 'Good' : 'Fair';
      $('imgDetailBy').textContent = pick.picked_by || '—';
      const az = Number(pick.dip_azimuth) * Math.PI / 180;
      const radius = 42 * (1 - Math.min(90, Number(pick.dip_angle)) / 90);
      const x = 56 + radius * Math.sin(az), y = 56 - radius * Math.cos(az);
      $('imgOrientationLine').setAttribute('d', `M56 56 L${x.toFixed(1)} ${y.toFixed(1)}`);
      $('imgOrientationDot').setAttribute('cx', x.toFixed(1)); $('imgOrientationDot').setAttribute('cy', y.toFixed(1));
    },

    renderVectorLayer() {
      const layer = $('imgVectorLayer');
      if (!layer) return;
      const a = this.state.asset;
      if (!a) { layer.innerHTML = ''; return; }
      const top = Number(a.depth_top), bottom = Number(a.depth_bottom), span = bottom - top || 1;
      const yFor = (depth) => Math.max(0, Math.min(MAX_H, (Number(depth) - top) / span * MAX_H));
      const xFor = (az) => ((Number(az) % 360 + 360) % 360) / 360 * MAX_W;
      const pieces = [];
      (a.dip_rows || []).forEach((pick) => {
        const amp = a.borehole_radius != null ? Math.tan(Number(pick.dip_angle) * Math.PI / 180) * Number(a.borehole_radius) / span * MAX_H : 0;
        const y0 = yFor(pick.depth), phase = Number(pick.dip_azimuth) * Math.PI / 180;
        let d = '';
        for (let x = 0; x <= MAX_W; x += 4) {
          const theta = x / MAX_W * Math.PI * 2;
          const y = y0 + amp * Math.cos(theta - phase);
          d += `${x === 0 ? 'M' : 'L'}${x} ${y.toFixed(2)} `;
        }
        const active = pick.id === this.state.selectedPick;
        pieces.push(`<path d="${d}" fill="none" stroke="var(--px-accent)" stroke-width="${active ? 2.4 : 1.3}" opacity="${active ? 1 : .55}" ${pick.approved ? '' : 'stroke-dasharray="4 3"'}/>`);
      });
      (this.state.trace || []).forEach((pt) => {
        const x = xFor(pt[1]), y = yFor(pt[0]);
        pieces.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6" fill="rgba(212,168,83,.15)" stroke="rgba(212,168,83,.7)"/><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.8" fill="var(--px-accent)" stroke="#131820" stroke-width="1.4"/>`);
      });
      layer.innerHTML = pieces.join('');
    },

    async onCanvasClick(event) {
      const a = this.state.asset;
      if (!a) return;
      const canvas = $('imgCanvas');
      const rect = canvas.getBoundingClientRect();
      const x = Math.max(0, Math.min(MAX_W, (event.clientX - rect.left) / rect.width * MAX_W));
      const y = Math.max(0, Math.min(MAX_H, (event.clientY - rect.top) / rect.height * MAX_H));
      const depth = Number(a.depth_top) + y / MAX_H * (Number(a.depth_bottom) - Number(a.depth_top));
      const az = x / MAX_W * 360;
      this.state.trace.push([Number(depth.toFixed(2)), Number(az.toFixed(1))]);
      $('imgPickHint').textContent = `${this.state.trace.length} trace point${this.state.trace.length === 1 ? '' : 's'} · need 3, spread ≥20°`;
      $('imgScaleNote').textContent = `${this.state.trace.length} trace points · need 3, spread ≥20°`;
      this.renderVectorLayer();
      if (this.state.trace.length > 12) this.state.trace.shift();
    },

    async fitDip() {
      const a = this.state.asset;
      if (!a) return GeoToast.warn('Select an image asset first.');
      if (!(Number(a.borehole_radius) > 0)) return GeoToast.warn('Borehole radius is required to fit a dip.');
      if (this.state.trace.length < 3) return GeoToast.warn('Click at least three trace points on the image.');
      try {
        const dip = await app._api(`/wells/${this.state.wid}/image-assets/${a.id}/dips`, {
          method: 'POST',
          body: JSON.stringify({ trace: this.state.trace, borehole_radius: Number(a.borehole_radius) }),
        });
        this.state.trace = [];
        GeoToast.success(`Dip ${num(dip.dip_angle, 1)}° / ${num(dip.dip_azimuth, 0)}° · R² ${num(dip.r2, 2)}`);
        await this.selectAsset(a.id);
        this.state.selectedPick = dip.id;
        this.renderPicks();
        this.renderVectorLayer();
        this.updateDetail(dip.id);
      } catch (e) { GeoToast.error(e.message); }
    },

    async approveOne(id, input) {
      if (!input.checked) { input.checked = true; return GeoToast.info('Dip approval is one-way.'); }
      try {
        await app._api(`/wells/${this.state.wid}/image-assets/${this.state.asset.id}/dips/${id}/approve`, { method: 'POST' });
        GeoToast.success('Dip pick approved');
        await this.selectAsset(this.state.asset.id);
      } catch (e) { input.checked = false; GeoToast.error(e.message); }
    },

    async approveAll() {
      const a = this.state.asset;
      if (!a) return;
      const pending = (a.dip_rows || []).filter((r) => !r.approved);
      if (!pending.length) return GeoToast.info('All picks are already approved.');
      try {
        for (const pick of pending) await app._api(`/wells/${this.state.wid}/image-assets/${a.id}/dips/${pick.id}/approve`, { method: 'POST' });
        GeoToast.success(`${pending.length} picks approved`);
        await this.selectAsset(a.id);
      } catch (e) { GeoToast.error(e.message); }
    },

    async upload(file) {
      if (!file) return;
      const top = Number($('imgDepthTop').value), bottom = Number($('imgDepthBottom').value), radius = Number($('imgUploadRadius').value);
      const validDepth = Number.isFinite(top) && Number.isFinite(bottom) && bottom > top;
      $('imgFileName').textContent = file.name;
      const fd = new FormData();
      fd.append('file', file);
      if (validDepth) { fd.append('depth_top', String(top)); fd.append('depth_bottom', String(bottom)); }
      fd.append('borehole_radius', String(radius || 0.15));
      fd.append('image_type', $('imgAssetType').value || 'manual');
      let endpoint = `/api/wells/${this.state.wid}/image-assets`;
      if (/\.dlis$/i.test(file.name)) {
        const channel = ($('imgChannel').value || '').trim();
        if (!channel) return GeoToast.warn('Enter the DLIS image channel.');
        fd.append('channel', channel);
        fd.append('depth_channel', 'DEPT');
        endpoint += '/import-dlis';
      } else if (/\.lis$/i.test(file.name)) {
        return GeoToast.warn('LIS image import is not implemented; use DLIS or a raster export.');
      } else if (!validDepth) {
        return GeoToast.warn('Set valid upload depth top/base.');
      } else {
        fd.append('source', file.name);
      }
      try {
        const resp = await fetch(endpoint, { method: 'POST', headers: app._authHeaders(), body: fd });
        const body = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(body.detail || `Upload failed (${resp.status})`);
        GeoToast.success(`Image asset uploaded · ${body.width || '?'} × ${body.height || '?'} px`);
        this.state.selectedId = body.id;
        await this.load();
      } catch (e) { GeoToast.error(e.message); }
    },

    editAsset() {
      const a = this.state.asset;
      if (!a) return GeoToast.warn('Select an image asset first.');
      PxModal.open({
        title: 'Edit image asset',
        body: `<div style="display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:10px">
            <label style="color:var(--px-muted);font-size:9px">Type<input id="imgEditType" class="px-text-control" value="${esc(a.image_type || '')}" style="width:100%;margin-top:3px"></label>
            <label style="color:var(--px-muted);font-size:9px">Source<input id="imgEditSource" class="px-text-control" value="${esc(a.source || '')}" style="width:100%;margin-top:3px"></label>
            <label style="color:var(--px-muted);font-size:9px">Depth top<input id="imgEditTop" class="px-text-control" type="number" step="0.1" value="${a.depth_top}" style="width:100%;margin-top:3px"></label>
            <label style="color:var(--px-muted);font-size:9px">Depth base<input id="imgEditBottom" class="px-text-control" type="number" step="0.1" value="${a.depth_bottom}" style="width:100%;margin-top:3px"></label>
            <label style="color:var(--px-muted);font-size:9px">Radius (m)<input id="imgEditRadius" class="px-text-control" type="number" step="0.001" value="${a.borehole_radius ?? ''}" style="width:100%;margin-top:3px"></label>
          </div>`,
        primaryLabel: 'Save asset',
        onPrimary: async () => {
          const payload = {
            image_type: document.getElementById('imgEditType').value,
            source: document.getElementById('imgEditSource').value,
            depth_top: Number(document.getElementById('imgEditTop').value),
            depth_bottom: Number(document.getElementById('imgEditBottom').value),
            borehole_radius: document.getElementById('imgEditRadius').value || null,
          };
          if (!(payload.depth_bottom > payload.depth_top)) return GeoToast.error('Depth base must exceed depth top.');
          try {
            await app._api(`/wells/${this.state.wid}/image-assets/${a.id}`, { method: 'PUT', body: JSON.stringify(payload) });
            PxModal.close();
            GeoToast.success('Image asset updated');
            await this.selectAsset(a.id);
            await this.load();
          } catch (e) { GeoToast.error(e.message); }
        },
      });
    },

    deleteAsset() {
      const a = this.state.asset;
      if (!a) return GeoToast.warn('Select an image asset first.');
      PxModal.open({
        title: 'Delete image asset',
        body: `<p>Delete <strong>${esc(a.image_type || 'image')}</strong> at ${num(a.depth_top, 1)}–${num(a.depth_bottom, 1)} m and all ${a.dip_rows?.length || 0} dip picks?</p><p>This removes the artifact file and cannot be undone.</p>`,
        primaryLabel: 'Delete asset',
        onPrimary: async () => {
          try {
            await app._api(`/wells/${this.state.wid}/image-assets/${a.id}`, { method: 'DELETE' });
            PxModal.close();
            GeoToast.success('Image asset deleted');
            this.state.selectedId = null;
            this.state.asset = null;
            await this.load();
          } catch (e) { GeoToast.error(e.message); }
        },
      });
    }
  };

  window.ImageLogView = View;
  document.addEventListener('DOMContentLoaded', () => {
    $('imgAsset')?.addEventListener('change', (e) => View.selectAsset(Number(e.target.value)));
    $('imgCanvas')?.addEventListener('click', (e) => View.onCanvasClick(e));
    $('imgFitBtn')?.addEventListener('click', () => View.fitDip());
    $('imgApproveBtn')?.addEventListener('click', () => View.approveAll());
    $('imgEditBtn')?.addEventListener('click', () => View.editAsset());
    $('imgDeleteBtn')?.addEventListener('click', () => View.deleteAsset());
    $('imgChooseFile')?.addEventListener('click', () => $('imgFile').click());
    $('imgFile')?.addEventListener('change', (e) => View.upload(e.target.files?.[0]));
    const bar = $('imgUploadBar');
    ['dragenter', 'dragover'].forEach((t) => bar?.addEventListener(t, (e) => { e.preventDefault(); bar.classList.add('px-dragover'); }));
    ['dragleave', 'drop'].forEach((t) => bar?.addEventListener(t, (e) => { e.preventDefault(); bar.classList.remove('px-dragover'); }));
    bar?.addEventListener('drop', (e) => View.upload(e.dataTransfer?.files?.[0]));
  });
})();
