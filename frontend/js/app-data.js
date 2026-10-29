/**
 * Well, tops, zones, operations and data-table methods for GeoLogApp.
 * Loaded after app.js and before bootstrap.js.
 */
Object.assign(GeoLogApp.prototype, {
    async createProject() {
        const r = await GeoModal.show({ title: 'New Project', fields: [
            { id: 'name', label: 'Project Name', placeholder: 'e.g. North Sea Study' },
        ]});
        if (!r?.name) return;
        try {
            await this._api('/projects/', {
                method: 'POST',
                body: JSON.stringify({ name: r.name, field_name: '', operator: '', country: '' }),
            });
            await this.loadProjects();
            GeoToast.success('Project created');
        } catch (e) { GeoToast.error('Failed to create project: ' + e.message); }
    },

    async deleteProject(id) {
        const r = await GeoModal.show({ title: 'Delete Project?', fields: [
            { id: 'confirm', label: 'This will delete all wells and data. Type DELETE to confirm:', placeholder: 'DELETE' },
        ]});
        if (r?.confirm !== 'DELETE') return;
        try {
            await this._api(`/projects/${id}`, { method: 'DELETE' });
            await this.loadProjects();
            GeoToast.success('Project deleted');
        } catch (e) { GeoToast.error('Failed to delete project: ' + e.message); }
    },

    async addWell() {
        if (!this.projects.length) return this.createProject();
        const r = await GeoModal.show({ title: 'Add Well', fields: [
            { id: 'name', label: 'Well Name', placeholder: 'e.g. MELANIE-1' },
            { id: 'uwi', label: 'UWI / API Number (optional)', placeholder: '42-123-45678' },
            { id: 'unit_system', label: 'Unit System', type: 'select', value: 'field', options: [{value:'field',label:'Field (ft, g/cc, us/ft)'},{value:'si',label:'SI (m, kg/m3, us/m)'}] },
        ]});
        if (!r?.name) return;
        try {
            await this._api('/wells/', {
                method: 'POST',
                body: JSON.stringify({ name: r.name, uwi: r.uwi || '', unit_system: r.unit_system || 'field', project_id: this.projects[0].id }),
            });
            await this.loadWells(this.projects[0].id);
            GeoToast.success('Well added');
        } catch (e) { GeoToast.error('Failed to add well: ' + e.message); }
    },

    async deleteWell(id) {
        const r = await GeoModal.show({ title: 'Delete Well?', fields: [
            { id: 'confirm', label: 'This will delete all log data. Type DELETE to confirm:', placeholder: 'DELETE' },
        ]});
        if (r?.confirm !== 'DELETE') return;
        try {
            await this._api(`/wells/${id}`, { method: 'DELETE' });
            if (this.projects.length > 0) await this.loadWells(this.projects[0].id);
            GeoToast.success('Well deleted');
        } catch (e) { GeoToast.error('Failed to delete well: ' + e.message); }
    },

    async deleteTop(id) {
        try {
            await this._api(`/tops/${id}`, { method: 'DELETE' });
            await this._loadFormationTops();
        } catch (e) { GeoToast.error('Failed to delete top: ' + e.message); }
    },

    async editTop(id) {
        const top = this.formationTops.find(t => t.id === id);
        if (!top) return;
        const r = await GeoModal.show({ title: 'Edit Formation Top', fields: [
            { id: 'formation_name', label: 'Formation Name', value: top.formation_name },
            { id: 'depth', label: 'Depth (ft)', type: 'number', step: '0.1', value: top.depth },
            { id: 'color', label: 'Color', type: 'color', value: top.color || '#f0883e' },
            { id: 'lithology', label: 'Lithology (optional)', value: top.lithology || '' },
        ]});
        if (!r?.formation_name || isNaN(parseFloat(r.depth))) return;
        try {
            await this._api(`/tops/${id}`, {
                method: 'PUT',
                body: JSON.stringify({
                    formation_name: r.formation_name,
                    depth: parseFloat(r.depth),
                    color: r.color || '#f0883e',
                    lithology: r.lithology || '',
                }),
            });
            await this._loadFormationTops();
            GeoToast.success('Formation top updated');
        } catch (e) { GeoToast.error('Failed to update top: ' + e.message); }
    },

    async addFormationTop() {
        if (!this.currentWell) return;
        const r = await GeoModal.show({ title: 'Add Formation Top', fields: [
            { id: 'name', label: 'Formation Name', placeholder: 'e.g. Top Reservoir' },
            { id: 'depth', label: 'Depth (ft)', type: 'number', step: '0.1', placeholder: '5000.0' },
            { id: 'base_depth', label: 'Base Depth (ft, optional)', type: 'number', step: '0.1', placeholder: '' },
            { id: 'color', label: 'Color', type: 'color', value: '#f0883e' },
            { id: 'lithology', label: 'Lithology (optional)', placeholder: 'e.g. Sandstone' },
        ]});
        if (!r?.name || isNaN(parseFloat(r.depth))) return;
        const payload = {
            formation_name: r.name,
            depth: parseFloat(r.depth),
            color: r.color || '#f0883e',
            lithology: r.lithology || '',
            depth_unit: 'FT',
        };
        if (r.base_depth && !isNaN(parseFloat(r.base_depth))) {
            payload.top_depth = parseFloat(r.depth);
            payload.base_depth = parseFloat(r.base_depth);
        }
        try {
            const created = await this._api(`/wells/${this.currentWell.id}/tops`, {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            await this._loadFormationTops();
            this._pushUndo('add_top', { top_id: created?.id, well_id: this.currentWell.id, payload });
        } catch (e) { GeoToast.error('Failed to add top: ' + e.message); }
    },

    async addFormationTopAtDepth(depth) {
        if (!this.currentWell || !Number.isFinite(depth) || depth < 0) return;
        const result = await GeoModal.show({
            title: `Add Formation Top at ${depth.toFixed(1)} ft`,
            fields: [
                { id: 'name', label: 'Formation Name', type: 'text', value: '', placeholder: 'e.g. SAND-A' },
                { id: 'color', label: 'Color', type: 'color', value: '#3fb950' },
                { id: 'lithology', label: 'Lithology', type: 'text', value: '', placeholder: 'e.g. Sandstone' }
            ]
        });
        if (!result?.name) return;
        try {
            const payload = {
                formation_name: result.name,
                depth,
                color: result.color || '#3fb950',
                lithology: result.lithology || '',
                depth_unit: 'FT'
            };
            const created = await this._api(`/wells/${this.currentWell.id}/tops`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            await this._loadFormationTops();
            this._pushUndo('add_top', { top_id: created?.id, well_id: this.currentWell.id, payload });
            GeoToast.success(`Top '${result.name}' added at ${depth.toFixed(1)} ft`);
        } catch (e) { GeoToast.error(e.message); }
    },

    async editCurrentWell() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const r = await GeoModal.show({ title: 'Edit Well', fields: [
            { id: 'name', label: 'Well Name', value: this.currentWell.name || '' },
            { id: 'uwi', label: 'UWI / API Number', value: this.currentWell.uwi || '' },
            { id: 'operator', label: 'Operator', value: this.currentWell.operator || '' },
            { id: 'field_name', label: 'Field Name', value: this.currentWell.field_name || '' },
            { id: 'depth_unit', label: 'Depth Unit', type: 'select', value: this.currentWell.depth_unit || 'FT', options: [{value:'FT',label:'Feet (FT)'},{value:'M',label:'Meters (M)'}] },
            { id: 'unit_system', label: 'Unit System', type: 'select', value: this.currentWell.unit_system || 'field', options: [{value:'field',label:'Field (ft, g/cc, us/ft)'},{value:'si',label:'SI (m, kg/m3, us/m)'}] },
        ]});
        if (!r?.name) return;
        try {
            await this._api(`/wells/${this.currentWell.id}`, {
                method: 'PUT',
                body: JSON.stringify({ name: r.name, uwi: r.uwi, operator: r.operator, field_name: r.field_name, depth_unit: r.depth_unit, unit_system: r.unit_system || 'field' }),
            });
            this.curveRangeCache?.clear();
            await this.loadWells(this.projects[0].id);
            await this._loadCurveData().catch(() => {});
            GeoToast.success('Well updated');
        } catch (e) { GeoToast.error('Failed to update well: ' + e.message); }
    },

    async _uploadLogFormatForWell(wellId, format = 'las') {
        const fm = String(format || 'las').toLowerCase();
        const conf = {
            las: { ext: '.las,.LAS', endpoint: 'upload-las', label: 'LAS' },
            dlis: { ext: '.dlis,.DLIS,.tif,.TIF', endpoint: 'upload-dlis', label: 'DLIS' },
            lis: { ext: '.lis,.LIS', endpoint: 'upload-lis', label: 'LIS' },
        }[fm] || { ext: '.las,.LAS', endpoint: 'upload-las', label: 'LAS' };

        const input = document.createElement('input');
        input.type = 'file';
        input.accept = conf.ext;
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            GeoLoading.show(`Uploading ${file.name}...`);
            try {
                const resp = await fetch(`/api/wells/${wellId}/${conf.endpoint}`, {
                    method: 'POST',
                    body: formData,
                    headers: this._authHeaders(),
                });
                if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
                const result = await resp.json();
                this._applyUploadedLASVersion(result);
                const runs = result.runs_created ? ` (${result.runs_created} run${result.runs_created > 1 ? 's' : ''})` : '';
                GeoToast.success(`Uploaded ${result.filename}${runs} — ${result.curves.length} curves, ${result.num_points} points`);
                if (Array.isArray(result.warnings) && result.warnings.length) {
                    GeoToast.warn(result.warnings.join('; '), 8000);
                }
                if (this.projects.length > 0) await this.loadWells(this.projects[0].id);
            } catch (e) {
                GeoToast.error(`${conf.label} upload failed: ` + e.message);
            } finally {
                GeoLoading.hide();
            }
        };
        input.click();
    },

    async uploadLAS() {
        if (!this.currentWell) return GeoToast.warn('Select or create a well first.');
        return this._uploadLogFormatForWell(this.currentWell.id, 'las');
    },

    async uploadDLIS() {
        if (!this.currentWell) return GeoToast.warn('Select or create a well first.');
        return this._uploadLogFormatForWell(this.currentWell.id, 'dlis');
    },

    async uploadLIS() {
        if (!this.currentWell) return GeoToast.warn('Select or create a well first.');
        return this._uploadLogFormatForWell(this.currentWell.id, 'lis');
    },

    async uploadLASForWell(wellId) {
        return this._uploadLogFormatForWell(wellId, 'las');
    },

    async uploadDLISForWell(wellId) {
        return this._uploadLogFormatForWell(wellId, 'dlis');
    },

    async uploadLISForWell(wellId) {
        return this._uploadLogFormatForWell(wellId, 'lis');
    },

    openBulkImportWizard() {
        if (!this.projects.length) {
            GeoToast.warn('Create a project first');
            return;
        }
        const modal = document.getElementById('bulkImportModal');
        if (!modal) return;
        modal.style.display = 'flex';
        this._initBulkUpload();
        this._resetBulkImportUI();
        if (typeof lucide !== 'undefined') lucide.createIcons();
    },

    closeBulkImportWizard(event) {
        if (event && event.target !== event.currentTarget) return;
        const modal = document.getElementById('bulkImportModal');
        if (modal) modal.style.display = 'none';
    },

    _resetBulkImportUI() {
        const list = document.getElementById('bulkImportList');
        const summary = document.getElementById('bulkImportSummary');
        if (list) list.innerHTML = '';
        if (summary) summary.textContent = 'Drop LAS files to begin.';
    },

    _parseLASWellName(text, fallbackName = '') {
        const lines = String(text || '').split(/\r?\n/);
        for (const line of lines) {
            const m = line.match(/^\s*WELL\s*\.[^:]*:\s*(.*?)\s*$/i);
            if (m?.[1]) return m[1].trim();
            const p = line.match(/^\s*WELL\s*\.\s*([^:]+?)\s*:/i);
            if (p?.[1]) return p[1].trim();
        }
        return (fallbackName || '').replace(/\.las$/i, '').trim() || 'UNKNOWN';
    },

    _isLASFile(file) {
        if (!file) return false;
        return /\.las$/i.test(file.name || '');
    },

    _renderBulkImportRows(items) {
        const list = document.getElementById('bulkImportList');
        if (!list) return;
        const statusColor = { pending: '#8b949e', parsing: '#d29922', uploading: '#58a6ff', done: '#3fb950', error: '#f85149' };
        list.innerHTML = items.map((item, idx) => {
            const prog = Math.max(0, Math.min(100, Number(item.progress || 0)));
            return `
                <div style="border:1px solid #30363d;border-radius:10px;padding:10px;margin-bottom:10px;background:#0d1117">
                    <div style="display:flex;justify-content:space-between;gap:10px;align-items:center">
                        <strong style="color:#c9d1d9">${escapeHtml(item.file.name)}</strong>
                        <span style="font-size:12px;color:${statusColor[item.status] || '#8b949e'}">${item.status.toUpperCase()}</span>
                    </div>
                    <div style="display:grid;grid-template-columns:1.5fr 1fr 1fr;gap:8px;font-size:12px;color:#8b949e;margin-top:6px">
                        <div>Well: <span style="color:#c9d1d9">${item.wellName || '-'}</span></div>
                        <div>Points: <span style="color:#c9d1d9">${item.pointsCount ?? '-'}</span></div>
                        <div>File #${idx + 1}</div>
                    </div>
                    <div style="height:8px;background:#161b22;border-radius:99px;overflow:hidden;margin-top:8px">
                        <div style="height:100%;width:${prog}%;background:${item.status === 'error' ? '#f85149' : '#58a6ff'};transition:width .2s ease"></div>
                    </div>
                    ${item.error ? `<div style="margin-top:6px;color:#f85149;font-size:12px">${item.error}</div>` : ''}
                </div>
            `;
        }).join('');
    },

    async _ensureWellByName(name) {
        const normalized = (name || '').trim();
        if (!normalized) throw new Error('Missing well name');
        const projectId = this.projects?.[0]?.id;
        if (!projectId) throw new Error('No project selected');
        let wells = [];
        try { wells = await this._api(`/wells/?project_id=${projectId}`); } catch { wells = this.wells || []; }
        const existing = (wells || []).find(w => (w.name || '').trim().toLowerCase() === normalized.toLowerCase());
        if (existing) return { well: existing, created: false };
        const created = await this._api('/wells/', {
            method: 'POST',
            body: JSON.stringify({ name: normalized, uwi: '', project_id: projectId }),
        });
        return { well: created, created: true };
    },

    _uploadLASWithProgress(wellId, file, onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', `/api/wells/${wellId}/upload-las`);
            const authH = this._authHeaders();
            for (const [k, v] of Object.entries(authH)) {
                xhr.setRequestHeader(k, v);
            }
            xhr.upload.onprogress = (evt) => {
                if (evt.lengthComputable && onProgress) onProgress(Math.round((evt.loaded / evt.total) * 100));
            };
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try { resolve(JSON.parse(xhr.responseText || '{}')); } catch { resolve({}); }
                } else {
                    let msg = `Upload failed: ${xhr.status}`;
                    try { const j = JSON.parse(xhr.responseText || '{}'); if (j.detail) msg = j.detail; } catch {}
                    reject(new Error(msg));
                }
            };
            xhr.onerror = () => reject(new Error('Network error during upload'));
            const fd = new FormData();
            fd.append('file', file);
            xhr.send(fd);
        });
    },

    async _startBulkImport(files) {
        const validFiles = Array.from(files || []).filter(f => this._isLASFile(f));
        if (!validFiles.length) return GeoToast.warn('Please select one or more .las files');

        const rows = validFiles.map(file => ({ file, status: 'pending', wellName: '', pointsCount: null, progress: 0, error: '' }));
        this._renderBulkImportRows(rows);

        let createdWells = 0, uploadedFiles = 0, errors = 0;
        GeoLoading.show(`Bulk importing ${validFiles.length} LAS file(s)...`);
        try {
            for (const row of rows) {
                try {
                    row.status = 'parsing'; row.progress = 5; this._renderBulkImportRows(rows);
                    const text = await row.file.text();
                    row.wellName = this._parseLASWellName(text, row.file.name);
                    const found = await this._ensureWellByName(row.wellName);
                    if (found.created) createdWells += 1;

                    row.status = 'uploading'; row.progress = 10; this._renderBulkImportRows(rows);
                    const result = await this._uploadLASWithProgress(found.well.id, row.file, (pct) => {
                        row.progress = Math.max(10, pct);
                        this._renderBulkImportRows(rows);
                    });

                    row.status = 'done';
                    row.progress = 100;
                    row.pointsCount = result?.num_points ?? row.pointsCount;
                    uploadedFiles += 1;
                } catch (e) {
                    row.status = 'error';
                    row.progress = 100;
                    row.error = e.message || String(e);
                    errors += 1;
                }
                this._renderBulkImportRows(rows);
            }

            const summary = document.getElementById('bulkImportSummary');
            if (summary) summary.innerHTML = `Done — <b>${createdWells}</b> wells created, <b>${uploadedFiles}</b> files uploaded, <b>${errors}</b> errors.`;
            GeoToast.info(`Bulk import done: ${uploadedFiles} uploaded, ${errors} errors`);
            if (this.projects?.length) await this.loadWells(this.projects[0].id);
        } finally {
            GeoLoading.hide();
        }
    },

    async addZone() {
        if (!this.renderer) return;
        const r = await GeoModal.show({ title: 'Add Zone', fields: [
            { id: 'name', label: 'Zone Name', placeholder: 'e.g. Pay Zone A' },
            { id: 'top', label: 'Top Depth (ft)', type: 'number', step: '0.1', placeholder: '5000.0' },
            { id: 'bottom', label: 'Bottom Depth (ft)', type: 'number', step: '0.1', placeholder: '5100.0' },
        ]});
        if (!r?.name || isNaN(parseFloat(r.top)) || isNaN(parseFloat(r.bottom))) return;
        const name = r.name, top = parseFloat(r.top), bottom = parseFloat(r.bottom);
        this._pushZoneHistory();
        const zonesBefore = JSON.parse(JSON.stringify(this.renderer.zones || []));
        const zonePayload = { name, top, bottom };
        const zones = [...zonesBefore, zonePayload];
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
        await this._loadZones();
        const createdZone = (this.renderer.zones || []).find(z => z.name === name && Math.abs(z.top - top) < 1e-6 && Math.abs(z.bottom - bottom) < 1e-6);
        const zonesAfter = JSON.parse(JSON.stringify(this.renderer.zones || []));
        this._pushUndo('add_zone', {
            zone_id: createdZone?.id,
            well_id: this.currentWell?.id,
            zone_payload: zonePayload,
            zones_before: zonesBefore,
            zones_after: zonesAfter,
        });
    },

    async removeZone(index) {
        this._pushZoneHistory();
        const zones = [...(this.renderer.zones || [])];
        zones.splice(index, 1);
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    },

    _renderZonesList() {
        const panel = document.getElementById('zonesPanel');
        if (!panel) return;
        const zones = this.renderer?.zones || [];
        const colors = this.renderer?.colors?.zoneColors || ['#1f6feb'];
        panel.innerHTML = zones.map((z, i) => `
            <div class="zone-row">
                <span class="zone-color" style="background:${z.color || colors[i % colors.length]}"></span>
                <span class="zone-name">${escapeHtml(z.name)}</span>
                <span class="zone-range">${z.top.toFixed(1)} – ${z.bottom.toFixed(1)}</span>
                <button class="btn-icon-sm" data-action="app.editZone" data-args='[${i}]' title="Edit">
                    <i data-lucide="pencil"></i>
                </button>
                <button class="btn-icon-sm" data-action="app.moveZoneUp" data-args='[${i}]' title="Move Up">
                    <i data-lucide="arrow-up"></i>
                </button>
                <button class="btn-icon-sm" data-action="app.moveZoneDown" data-args='[${i}]' title="Move Down">
                    <i data-lucide="arrow-down"></i>
                </button>
                <button class="btn-icon-sm" data-action="app.splitZone" data-args='[${i}]' title="Split">
                    <i data-lucide="split"></i>
                </button>
                <button class="btn-icon-sm" data-action="app.mergeZone" data-args='[${i}]' title="Merge Next">
                    <i data-lucide="merge"></i>
                </button>
                <button class="btn-icon-sm" data-action="app.removeZone" data-args='[${i}]' title="Remove">
                    <i data-lucide="x"></i>
                </button>
            </div>
        `).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    },

    async editZone(index) {
        const zones = [...(this.renderer.zones || [])];
        const z = zones[index];
        if (!z) return;
        const r = await GeoModal.show({ title: 'Edit Zone', fields: [
            { id: 'name', label: 'Zone Name', value: z.name },
            { id: 'top', label: 'Top Depth (ft)', type: 'number', step: '0.1', value: z.top },
            { id: 'bottom', label: 'Bottom Depth (ft)', type: 'number', step: '0.1', value: z.bottom },
        ]});
        if (!r?.name || isNaN(parseFloat(r.top)) || isNaN(parseFloat(r.bottom))) return;
        const top = parseFloat(r.top), bottom = parseFloat(r.bottom);
        if (bottom <= top) return GeoToast.warn('Bottom must be > Top');
        this._pushZoneHistory();
        zones[index] = { ...z, name: r.name, top, bottom };
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    },

    async splitZone(index) {
        const zones = [...(this.renderer.zones || [])];
        const z = zones[index];
        if (!z) return;
        const midDefault = ((z.top + z.bottom) / 2).toFixed(1);
        const r = await GeoModal.show({ title: 'Split Zone', fields: [
            { id: 'depth', label: `Split depth (${z.top.toFixed(1)}-${z.bottom.toFixed(1)})`, type: 'number', step: '0.1', value: midDefault },
        ]});
        const d = parseFloat(r?.depth);
        if (!Number.isFinite(d) || d <= z.top || d >= z.bottom) return GeoToast.warn('Invalid split depth');
        this._pushZoneHistory();
        zones.splice(index, 1, { ...z, name: `${z.name}-A`, bottom: d }, { ...z, name: `${z.name}-B`, top: d });
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    },

    async moveZoneUp(index) {
        const zones = [...(this.renderer.zones || [])];
        if (index <= 0 || index >= zones.length) return;
        this._pushZoneHistory();
        [zones[index - 1], zones[index]] = [zones[index], zones[index - 1]];
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    },

    async moveZoneDown(index) {
        const zones = [...(this.renderer.zones || [])];
        if (index < 0 || index >= zones.length - 1) return;
        this._pushZoneHistory();
        [zones[index], zones[index + 1]] = [zones[index + 1], zones[index]];
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    },

    async mergeZone(index) {
        const zones = [...(this.renderer.zones || [])];
        if (index < 0 || index >= zones.length - 1) return GeoToast.warn('No next zone to merge');
        this._pushZoneHistory();
        const a = zones[index];
        const b = zones[index + 1];
        const merged = {
            ...a,
            name: `${a.name}+${b.name}`,
            top: Math.min(a.top, b.top),
            bottom: Math.max(a.bottom, b.bottom),
        };
        zones.splice(index, 2, merged);
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
        GeoToast.success('Zones merged');
    },

    async loadDepthShift() {
        const runId = document.getElementById('depthShiftRun')?.value;
        if (!runId) return;
        try {
            const ds = await this._api('/log-runs/' + runId + '/depth-shift');
            const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
            set('depthShiftVal', ds.shift || 0);
            set('depthStretchVal', ds.stretch || 1);
        } catch {}
    },

    async saveDepthShift() {
        const runId = document.getElementById('depthShiftRun')?.value;
        if (!runId) return GeoToast.warn('Select a log run');
        const shift = parseFloat(document.getElementById('depthShiftVal')?.value || '0');
        const stretch = parseFloat(document.getElementById('depthStretchVal')?.value || '1');
        await this._api('/log-runs/' + runId + '/depth-shift', {
            method: 'POST',
            body: JSON.stringify({ shift, stretch }),
        });
        this.curveRangeCache?.clear();
        await this._loadCurveData().catch(() => {});
        GeoToast.success('Depth shift saved: ' + shift + ' ft, stretch ' + stretch);
    },

    async editDepthControlPoints() {
        await this._populateToolRunSelectors();
        const runId = document.getElementById('depthShiftRun')?.value;
        if (!runId) return GeoToast.warn('Select a log run');
        let points = [];
        try { points = await this._api('/log-runs/' + runId + '/depth-control-points'); } catch {}
        const text = (points || []).map(p => `${p.md}, ${p.corrected_depth}`).join(String.fromCharCode(10));
        const r = await GeoModal.show({
            title: 'Depth Control Points',
            fields: [{
                id: 'points', type: 'textarea', rows: 8,
                label: 'MD, corrected depth — one pair per line',
                value: text,
            }],
        });
        if (!r) return;
        const parsed = String(r.points || '')
            .split(String.fromCharCode(10)).map(line => line.trim()).filter(Boolean)
            .map(line => line.split(',').map(v => parseFloat(v.trim())))
            .filter(pair => pair.length === 2 && pair.every(Number.isFinite))
            .map(pair => ({ md: pair[0], corrected_depth: pair[1] }));
        try {
            if (parsed.length === 0) {
                await this._api('/log-runs/' + runId + '/depth-control-points', { method: 'DELETE' });
                GeoToast.info('Control points cleared');
            } else {
                await this._api('/log-runs/' + runId + '/depth-control-points', {
                    method: 'PUT',
                    body: JSON.stringify({ points: parsed }),
                });
                GeoToast.success(`Saved ${parsed.length} control points`);
            }
            this.curveRangeCache?.clear();
            await this._loadCurveData().catch(() => {});
        } catch (e) { GeoToast.error('Control points failed: ' + e.message); }
    },

    async runSplice() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const curve = document.getElementById('spliceCurve')?.value || 'GR';
        const runA = parseInt(document.getElementById('spliceRunA')?.value || '0');
        const runB = parseInt(document.getElementById('spliceRunB')?.value || '0');
        const from = parseFloat(document.getElementById('spliceFrom')?.value || '0');
        const to = parseFloat(document.getElementById('spliceTo')?.value || '0');
        if (!runA || !runB || to <= from) return GeoToast.warn('Set valid runs and depth range');
        GeoLoading.show('Splicing ' + curve + '...');
        try {
            const result = await this._api('/wells/' + this.currentWell.id + '/splice', {
                method: 'POST',
                body: JSON.stringify({
                    source_runs: [runA, runB],
                    intervals: [
                        { start: 0, end: from, source_lr_id: runA },
                        { start: from, end: to, source_lr_id: runB },
                        { start: to, end: 99999, source_lr_id: runA },
                    ],
                    mnemonic: curve,
                }),
            });
            GeoToast.success('Spliced run created: ' + result.log_run_id + ' (' + result.points + ' pts)');
            await this.selectWell(this.currentWell.id);
            await this._populateToolRunSelectors();
        } catch (e) {
            GeoToast.error('Splice failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    async loadAnnotations() {
        if (!this.currentWell) return;
        try {
            const anns = await this._api('/wells/' + this.currentWell.id + '/annotations');
            const panel = document.getElementById('annotationsList');
            if (!panel) return;
            if (!anns.length) { panel.innerHTML = '<p style="color:#8b949e">No annotations</p>'; return; }
            panel.innerHTML = anns.map(a =>
                '<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid #21262d">' +
                '<span style="color:' + (a.color || '#f39c12') + ';font-weight:600">' + (a.depth?.toFixed(1) || '?') + ' ft</span>' +
                '<span style="flex:1;color:#c9d1d9">' + (a.text || '') + '</span>' +
                '<span style="color:#8b949e;font-size:10px">' + (a.annotation_type || 'note') + '</span>' +
                '<button class="btn-icon-sm" data-ann-id="' + a.id + '" title="Delete"><i data-lucide="x"></i></button>' +
                '</div>'
            ).join('');
            if (typeof lucide !== 'undefined') lucide.createIcons();
        } catch {}
    },

    async addAnnotation() {
        const r = await GeoModal.show({ title: 'Add Annotation', fields: [
            { id: 'depth', label: 'Depth (ft)', type: 'number', step: '0.1', placeholder: '5000.0' },
            { id: 'text', label: 'Note', placeholder: 'Enter annotation text...' },
            { id: 'type', label: 'Type', type: 'select', options: [
                { value: 'note', label: 'Note' }, { value: 'flag', label: 'Flag' }, { value: 'pay', label: 'Pay Zone' }, { value: 'issue', label: 'Issue' },
            ], value: 'note' },
        ]});
        if (!r?.text || isNaN(parseFloat(r.depth))) return;
        const payload = { depth: parseFloat(r.depth), text: r.text, annotation_type: r.type || 'note' };
        const created = await this._api('/wells/' + this.currentWell.id + '/annotations', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        this._pushUndo('add_annotation', { annotation_id: created?.id, well_id: this.currentWell.id, payload });
        GeoToast.success('Annotation added');
        await this.loadAnnotations();
    },

    async deleteAnnotation(aid) {
        await this._api('/annotations/' + aid, { method: 'DELETE' });
        await this.loadAnnotations();
    },

    async loadDST() {
        if (!this.currentWell) return;
        GeoLoading.show('Loading DST data...');
        try {
            const rows = await this._api('/wells/' + this.currentWell.id + '/dst');
            this.dstData = Array.isArray(rows) ? rows : [];
            const panel = document.getElementById('dstList');
            if (panel) {
                if (!this.dstData.length) panel.innerHTML = '<p style="color:#8b949e">No DST data</p>';
                else panel.innerHTML = this.dstData.map(d =>
                    '<div style="border-bottom:1px solid #21262d;padding:6px 0">' +
                    '<div><strong>' + (d.test_number || 'DST') + '</strong> ' + (d.formation || '') + '</div>' +
                    '<div style="color:#8b949e">' + Number(d.top_depth).toFixed(1) + ' - ' + Number(d.bottom_depth).toFixed(1) + ' ft | SIP ' + (d.shut_in_pressure ?? '-') + ' | FP ' + (d.flowing_pressure ?? '-') + '</div>' +
                    '</div>'
                ).join('');
            }
            if (this.renderer) {
                this.renderer.dstIntervals = this.dstData;
                this.renderer.render();
            }
        } catch {}
        finally { GeoLoading.hide(); }
    },

    async addDST() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const r = await GeoModal.show({ title: 'Add DST Test', fields: [
            { id: 'test_number', label: 'Test Number' },
            { id: 'formation', label: 'Formation' },
            { id: 'top_depth', label: 'Top Depth (ft)', type: 'number', step: '0.1' },
            { id: 'bottom_depth', label: 'Bottom Depth (ft)', type: 'number', step: '0.1' },
            { id: 'shut_in_pressure', label: 'Shut-in Pressure', type: 'number', step: '0.1' },
            { id: 'flowing_pressure', label: 'Flowing Pressure', type: 'number', step: '0.1' },
            { id: 'result', label: 'Result' },
            { id: 'notes', label: 'Notes' },
        ]});
        if (!r || isNaN(parseFloat(r.top_depth)) || isNaN(parseFloat(r.bottom_depth))) return;
        await this._api('/wells/' + this.currentWell.id + '/dst', { method: 'POST', body: JSON.stringify(r) });
        GeoToast.success('DST saved');
        await this.loadDST();
    },

    async loadRFT() {
        if (!this.currentWell) return;
        GeoLoading.show('Loading RFT data...');
        try {
            const rows = await this._api('/wells/' + this.currentWell.id + '/rft');
            this.rftData = Array.isArray(rows) ? rows : [];
            this.rftGradientAnalysis = await this._api('/wells/' + this.currentWell.id + '/rft/pressure-gradient').catch(() => null);
            if (this.renderer) {
                this.renderer.rftPoints = this.rftData;
                this.renderer.render();
            }
            await this._drawRFTCrossplot();
            this._renderRFTAnalysisSummary();
        } catch {}
        finally { GeoLoading.hide(); }
    },

    _renderRFTAnalysisSummary() {
        const summaryEl = document.getElementById('rftAnalysisSummary');
        const tableEl = document.getElementById('rftContactsTable');
        if (!summaryEl || !tableEl) return;
        const grad = this.rftGradientAnalysis;
        if (!grad || !grad.count) {
            summaryEl.innerHTML = '<div style="color:#8b949e">No gradient analysis available</div>';
            tableEl.innerHTML = '';
            return;
        }
        const reg = grad.pressure_regime_summary || {};
        const overall = grad.overall || {};
        const fmt = (v, n = 3) => Number.isFinite(Number(v)) ? Number(v).toFixed(n) : '-';
        summaryEl.innerHTML =
            `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;font-size:12px">` +
            `<div><b>Overall Gradient</b><br>${fmt(overall.gradient, 4)} psi/ft</div>` +
            `<div><b>Fluid Guess</b><br>${overall.fluid_guess || 'unknown'}</div>` +
            `<div><b>Regime</b><br>${overall.regime || 'unknown'}</div>` +
            `<div><b>Contacts</b><br>${(grad.fluid_contacts || []).length}</div>` +
            `<div><b>Normal</b><br>${reg.normal || 0}</div>` +
            `<div><b>Underpressure</b><br>${reg.underpressure || 0}</div>` +
            `<div><b>Overpressure</b><br>${reg.overpressure || 0}</div>` +
            `</div>`;

        const contacts = grad.fluid_contacts || [];
        const segs = grad.fluid_segments || [];
        let html = '<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>' +
            '<th style="text-align:left;padding:6px;border-bottom:1px solid #30363d">Type</th>' +
            '<th style="text-align:left;padding:6px;border-bottom:1px solid #30363d">Depth (ft)</th>' +
            '<th style="text-align:left;padding:6px;border-bottom:1px solid #30363d">From→To</th>' +
            '<th style="text-align:left;padding:6px;border-bottom:1px solid #30363d">Segment Gradient</th>' +
            '</tr></thead><tbody>';
        if (!contacts.length) {
            html += '<tr><td colspan="4" style="padding:6px;color:#8b949e">No fluid contacts identified</td></tr>';
        } else {
            contacts.forEach((c, i) => {
                const g = segs[i]?.gradient;
                html += '<tr>' +
                    `<td style="padding:6px;border-bottom:1px solid #21262d">${c.type || '-'}</td>` +
                    `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(c.depth, 1)}</td>` +
                    `<td style="padding:6px;border-bottom:1px solid #21262d">${(c.from_fluid || '-')}→${(c.to_fluid || '-')}</td>` +
                    `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(g, 4)} psi/ft</td>` +
                    '</tr>';
            });
        }
        html += '</tbody></table></div>';
        tableEl.innerHTML = html;
    },

    async addRFT() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const r = await GeoModal.show({ title: 'Add RFT Point', fields: [
            { id: 'depth', label: 'Depth (ft)', type: 'number', step: '0.1' },
            { id: 'pressure', label: 'Pressure', type: 'number', step: '0.1' },
            { id: 'fluid_type', label: 'Fluid Type', type: 'select', options: [
                { value: 'oil', label: 'Oil' },
                { value: 'gas', label: 'Gas' },
                { value: 'water', label: 'Water' },
            ], value: 'oil' },
            { id: 'mobility', label: 'Mobility', type: 'number', step: '0.01' },
            { id: 'notes', label: 'Notes' },
        ]});
        if (!r || isNaN(parseFloat(r.depth)) || isNaN(parseFloat(r.pressure))) return;
        await this._api('/wells/' + this.currentWell.id + '/rft', { method: 'POST', body: JSON.stringify(r) });
        GeoToast.success('RFT point saved');
        await this.loadRFT();
    },

    _initRFTCSVUpload() {
        const input = document.getElementById('rftCsvFileInput');
        if (!input || input._bound) return;
        input._bound = true;
        input.addEventListener('change', async () => {
            const file = input.files?.[0];
            if (!file || !this.currentWell) return;
            const status = document.getElementById('rftUploadStatus');
            if (status) status.textContent = 'Uploading ' + file.name + '...';
            const formData = new FormData();
            formData.append('file', file);
            GeoLoading.show(`Uploading ${file.name}...`);
            try {
                const resp = await fetch('/api/wells/' + this.currentWell.id + '/rft/upload-csv', {
                    method: 'POST',
                    body: formData,
                    headers: this._authHeaders(),
                });
                const result = await resp.json();
                if (resp.ok) {
                    if (status) status.textContent = 'Inserted ' + (result.inserted || 0) + ' RFT rows';
                    GeoToast.success('RFT CSV uploaded');
                    await this.loadRFT();
                } else {
                    if (status) status.textContent = 'Upload failed';
                    GeoToast.error(result?.detail || result?.message || 'RFT CSV upload failed');
                }
            } catch (e) {
                if (status) status.textContent = 'Upload failed';
                GeoToast.error('RFT CSV upload failed: ' + (e.message || e));
            } finally {
                GeoLoading.hide();
                input.value = '';
            }
        });
    },

    async _drawRFTCrossplot() {
        const canvas = document.getElementById('rftCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.parentElement?.clientWidth || 600;
        canvas.height = 320;
        const W = canvas.width, H = canvas.height;
        const m = { top: 20, right: 20, bottom: 36, left: 56 };
        const pw = W - m.left - m.right;
        const ph = H - m.top - m.bottom;
        ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, H);
        if (!this.rftData.length) { ctx.fillStyle = '#8b949e'; ctx.fillText('No RFT data', 20, 30); return; }
        const pVals = this.rftData.map(r => Number(r.pressure)).filter(v => Number.isFinite(v));
        const dVals = this.rftData.map(r => Number(r.depth)).filter(v => Number.isFinite(v));
        const pMin = Math.min(...pVals), pMax = Math.max(...pVals);
        const dMin = Math.min(...dVals), dMax = Math.max(...dVals);
        const sx = p => m.left + ((p - pMin) / ((pMax - pMin) || 1)) * pw;
        const sy = d => m.top + ((d - dMin) / ((dMax - dMin) || 1)) * ph;
        const fc = f => (f === 'oil' ? '#2ecc71' : f === 'gas' ? '#e74c3c' : f === 'water' ? '#3498db' : '#aaaaaa');
        const regimeColor = r => (r === 'normal' ? '#58a6ff' : r === 'underpressure' ? '#ffb86b' : r === 'overpressure' ? '#ff6b6b' : '#9aa0a6');

        ctx.strokeStyle = '#21262d'; ctx.lineWidth = 1; ctx.strokeRect(m.left, m.top, pw, ph);
        const clsByDepthPressure = new Map();
        for (const cp of (this.rftGradientAnalysis?.classified_points || [])) {
            clsByDepthPressure.set(`${Number(cp.depth).toFixed(3)}|${Number(cp.pressure).toFixed(3)}`, cp);
        }
        for (const r of this.rftData) {
            const x = sx(Number(r.pressure));
            const y = sy(Number(r.depth));
            const key = `${Number(r.depth).toFixed(3)}|${Number(r.pressure).toFixed(3)}`;
            const cp = clsByDepthPressure.get(key);
            ctx.fillStyle = fc((cp?.fluid_from_gradient || r.fluid_type || '').toLowerCase());
            ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
            if (cp?.pressure_regime) {
                ctx.strokeStyle = regimeColor(cp.pressure_regime);
                ctx.lineWidth = 1.5;
                ctx.stroke();
            }
        }

        try {
            const grad = this.rftGradientAnalysis || await this._api('/wells/' + this.currentWell.id + '/rft/pressure-gradient');
            this.rftGradientAnalysis = grad;
            const lines = [];
            if (grad.overall) lines.push({ ...grad.overall, color: '#f2cc60', label: 'Best fit' });
            if (grad.gradient_lines?.hydrostatic) lines.push({ ...grad.gradient_lines.hydrostatic, color: '#58a6ff' });
            if (grad.gradient_lines?.lithostatic) lines.push({ ...grad.gradient_lines.lithostatic, color: '#a371f7' });
            for (const g of (grad.fluid_segments || [])) lines.push({ ...g, color: fc(g.fluid_type), label: `${g.fluid_type} ${Number(g.gradient).toFixed(3)}` });
            for (const ln of lines) {
                const y1d = dMin, y2d = dMax;
                const x1p = ln.gradient * y1d + ln.intercept;
                const x2p = ln.gradient * y2d + ln.intercept;
                ctx.strokeStyle = ln.color; ctx.lineWidth = 1.5;
                ctx.beginPath(); ctx.moveTo(sx(x1p), sy(y1d)); ctx.lineTo(sx(x2p), sy(y2d)); ctx.stroke();
                if (ln.label) {
                    ctx.fillStyle = ln.color;
                    ctx.font = '10px DM Sans';
                    ctx.fillText(ln.label, Math.min(W - 80, sx(x2p) + 4), Math.max(12, sy(y2d) - 4));
                }
            }
            for (const c of (grad.fluid_contacts || [])) {
                const y = sy(Number(c.depth));
                ctx.setLineDash([4, 3]);
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(m.left, y);
                ctx.lineTo(m.left + pw, y);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = '#ffffff';
                ctx.font = '10px DM Sans';
                ctx.fillText(`Contact ${c.type} @ ${Number(c.depth).toFixed(1)} ft`, m.left + 6, y - 4);
            }
        } catch {}

        ctx.fillStyle = '#c9d1d9'; ctx.font = '11px DM Sans'; ctx.textAlign = 'center';
        ctx.fillText('Pressure', m.left + pw / 2, H - 8);
        ctx.save(); ctx.translate(14, m.top + ph / 2); ctx.rotate(-Math.PI / 2); ctx.fillText('Depth (ft)', 0, 0); ctx.restore();
    },

    async loadCompletion() {
        if (!this.currentWell) return;
        try {
            const rows = await this._api('/wells/' + this.currentWell.id + '/completion');
            this.completionData = Array.isArray(rows) ? rows : [];
            this.renderer?.setCompletionData(this.completionData);
            this._renderCompletionList();
        } catch {
            this.completionData = [];
            this._renderCompletionList();
        }
    },

    _renderCompletionList() {
        const el = document.getElementById('completionList');
        if (!el) return;
        if (!this.completionData.length) {
            el.innerHTML = '<p style="color:#8b949e">No completion components</p>';
            return;
        }
        el.innerHTML = this.completionData.map(c =>
            `<div style="display:grid;grid-template-columns:1fr auto;gap:6px;padding:6px 0;border-bottom:1px solid #21262d">` +
            `<div><strong>${(c.component_type || '').toUpperCase()}</strong> ${c.size ? '(' + c.size + ')' : ''}<br><span style="color:#8b949e">${Number(c.depth_top).toFixed(1)} - ${Number(c.depth_base).toFixed(1)} ft</span></div>` +
            `<button class="btn-icon-sm" data-action="app.deleteCompletionComponent" data-args='[${c.id}]' title="Delete"><i data-lucide="x"></i></button>` +
            `</div>`
        ).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    },

    async addCompletionComponent() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const r = await GeoModal.show({ title: 'Add Completion Component', fields: [
            { id: 'component_type', label: 'Type', type: 'select', options: [
                { value: 'casing', label: 'Casing' }, { value: 'tubing', label: 'Tubing' }, { value: 'packer', label: 'Packer' },
                { value: 'perforation', label: 'Perforation' }, { value: 'screen', label: 'Screen' }, { value: 'liner', label: 'Liner' },
                { value: 'cement', label: 'Cement' }, { value: 'pump', label: 'Pump' }, { value: 'valve', label: 'Valve' },
            ], value: 'casing' },
            { id: 'depth_top', label: 'Depth Top (ft)', type: 'number', step: '0.1' },
            { id: 'depth_base', label: 'Depth Base (ft)', type: 'number', step: '0.1' },
            { id: 'size', label: 'Size (e.g., 7 in)' },
            { id: 'description', label: 'Description' },
        ]});
        if (!r || isNaN(parseFloat(r.depth_top)) || isNaN(parseFloat(r.depth_base))) return;
        await this._api('/wells/' + this.currentWell.id + '/completion', { method: 'POST', body: JSON.stringify(r) });
        GeoToast.success('Completion component added');
        await this.loadCompletion();
    },

    async deleteCompletionComponent(cid) {
        await this._api('/completion/' + cid, { method: 'DELETE' });
        await this.loadCompletion();
    },

    async uploadCompletionCSV() {
        const input = document.getElementById('completionCsvFileInput');
        const file = input?.files?.[0];
        if (!file || !this.currentWell) return;
        const status = document.getElementById('completionUploadStatus');
        if (status) status.textContent = 'Uploading ' + file.name + '...';
        const formData = new FormData();
        formData.append('file', file);
        try {
            const resp = await fetch('/api/wells/' + this.currentWell.id + '/completion/upload-csv', {
                method: 'POST',
                body: formData,
                headers: this._authHeaders(),
            });
            const result = await resp.json();
            if (!resp.ok) throw new Error(result?.detail || 'Upload failed');
            if (status) status.textContent = `Inserted ${result.inserted || 0} rows`;
            GeoToast.success('Completion CSV uploaded');
            await this.loadCompletion();
        } catch (e) {
            if (status) status.textContent = 'Upload failed';
            GeoToast.error('Completion upload failed: ' + (e.message || e));
        } finally {
            if (input) input.value = '';
        }
    },

    toggleCompletionTrack(enabled = !this.showCompletionTrack) {
        this.showCompletionTrack = !!enabled;
        this.renderer?.setCompletionTrackVisible(this.showCompletionTrack);
    },

    async loadProduction() {
        if (!this.currentWell) return;
        GeoLoading.show('Loading production data...');
        try {
            this.productionData = await this._api('/wells/' + this.currentWell.id + '/production').catch(() => []);
            this.productionDecline = await this._api('/wells/' + this.currentWell.id + '/production/decline-curve').catch(() => null);
            this._renderProductionTable();
            this._drawProductionCharts();
            const eur = document.getElementById('productionEUR');
            if (eur) {
                const v = this.productionDecline?.eur_oil_bbl;
                eur.textContent = Number.isFinite(v) ? `EUR: ${Math.round(v).toLocaleString()} bbl (${this.productionDecline?.best_model || 'n/a'})` : 'EUR: n/a';
            }
        } catch {}
        finally { GeoLoading.hide(); }
    },

    _renderProductionTable() {
        const el = document.getElementById('productionTable');
        if (!el) return;
        const rows = this.productionData || [];
        if (!rows.length) {
            el.innerHTML = '<p style="color:#8b949e">No production data</p>';
            return;
        }
        const hdr = ['Date','Oil','Gas','Water','WCut%','GOR','BHP','WHP','Choke','CumOil','CumGas','CumWater'];
        let html = '<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>';
        html += hdr.map(h => `<th style="text-align:left;padding:6px;border-bottom:1px solid #30363d">${h}</th>`).join('');
        html += '</tr></thead><tbody>';
        for (const r of rows) {
            const fmt = (v, n=2) => (v === null || v === undefined || v === '') ? '-' : Number(v).toFixed(n);
            html += '<tr>' +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${r.date || ''}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.oil_rate)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.gas_rate)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.water_rate)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.water_cut,1)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.gor,1)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.bhp,1)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.whp,1)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.choke_size,1)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.cumulative_oil,1)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.cumulative_gas,1)}</td>` +
                `<td style="padding:6px;border-bottom:1px solid #21262d">${fmt(r.cumulative_water,1)}</td>` +
                '</tr>';
        }
        html += '</tbody></table></div>';
        el.innerHTML = html;
    },

    _drawProductionCharts() {
        const draw = (canvasId, series, yLabel, overlay = null) => {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.parentElement?.clientWidth || 900;
            const W = canvas.width, H = canvas.height;
            const m = { top: 16, right: 16, bottom: 30, left: 52 };
            const pw = W - m.left - m.right, ph = H - m.top - m.bottom;
            ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, H);
            const rows = this.productionData || [];
            if (!rows.length) { ctx.fillStyle = '#8b949e'; ctx.fillText('No data', 20, 24); return; }
            const xs = rows.map((_, i) => i);
            const vals = series.flatMap(s => rows.map(r => Number(r[s.key])).filter(Number.isFinite));
            if (!vals.length) return;
            const ymin = Math.min(...vals), ymax = Math.max(...vals);
            const sx = i => m.left + (i / Math.max(1, xs.length - 1)) * pw;
            const sy = v => m.top + (1 - ((v - ymin) / ((ymax - ymin) || 1))) * ph;
            ctx.strokeStyle = '#21262d'; ctx.strokeRect(m.left, m.top, pw, ph);
            for (const s of series) {
                ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.beginPath();
                let started = false;
                rows.forEach((r, i) => {
                    const v = Number(r[s.key]);
                    if (!Number.isFinite(v)) return;
                    const x = sx(i), y = sy(v);
                    if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
                });
                ctx.stroke();
            }
            if (overlay) {
                ctx.setLineDash([5, 4]); ctx.strokeStyle = overlay.color || '#ffffff'; ctx.lineWidth = 2; ctx.beginPath();
                let started = false;
                rows.forEach((r, i) => {
                    const p = overlay.lookup?.[r.date];
                    if (!Number.isFinite(p)) return;
                    const x = sx(i), y = sy(p);
                    if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
                });
                ctx.stroke();
                ctx.setLineDash([]);
            }
            ctx.fillStyle = '#c9d1d9'; ctx.font = '11px DM Sans'; ctx.fillText(yLabel, 8, 14);
        };

        const fitLookup = {};
        for (const p of (this.productionDecline?.fitted_points || [])) fitLookup[p.date] = Number(p.q_fit);
        draw('productionCanvas', [
            { key: 'oil_rate', color: '#2ecc71' },
            { key: 'gas_rate', color: '#e74c3c' },
            { key: 'water_rate', color: '#3498db' },
            { key: 'water_cut', color: '#f2cc60' },
        ], 'Rates', { color: '#ffffff', lookup: fitLookup });
        draw('productionPressureCanvas', [
            { key: 'bhp', color: '#5bc0de' },
            { key: 'whp', color: '#b46fff' },
        ], 'Pressure (psi)');
    },

    async addProductionRecord() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const r = await GeoModal.show({ title: 'Add Production Record', fields: [
            { id: 'date', label: 'Date (YYYY-MM-DD)', value: new Date().toISOString().slice(0,10) },
            { id: 'oil_rate', label: 'Oil Rate (bbl/d)', type: 'number', step: '0.01' },
            { id: 'gas_rate', label: 'Gas Rate (mcf/d)', type: 'number', step: '0.01' },
            { id: 'water_rate', label: 'Water Rate (bbl/d)', type: 'number', step: '0.01' },
            { id: 'water_cut', label: 'Water Cut (%)', type: 'number', step: '0.01' },
            { id: 'gor', label: 'GOR (scf/bbl)', type: 'number', step: '0.01' },
            { id: 'bhp', label: 'BHP (psi)', type: 'number', step: '0.01' },
            { id: 'whp', label: 'WHP (psi)', type: 'number', step: '0.01' },
            { id: 'choke_size', label: 'Choke Size (64ths)', type: 'number', step: '0.01' },
            { id: 'cumulative_oil', label: 'Cumulative Oil', type: 'number', step: '0.01' },
            { id: 'cumulative_gas', label: 'Cumulative Gas', type: 'number', step: '0.01' },
            { id: 'cumulative_water', label: 'Cumulative Water', type: 'number', step: '0.01' },
            { id: 'notes', label: 'Notes' },
        ]});
        if (!r || !r.date) return;
        await this._api('/wells/' + this.currentWell.id + '/production', { method: 'POST', body: JSON.stringify(r) });
        GeoToast.success('Production record saved');
        await this.loadProduction();
    },

    _initProductionCSVUpload() {
        const input = document.getElementById('productionCsvFileInput');
        if (!input || input._boundProd) return;
        input._boundProd = true;
        input.addEventListener('change', async () => {
            const file = input.files?.[0];
            if (!file || !this.currentWell) return;
            const status = document.getElementById('productionUploadStatus');
            if (status) status.textContent = 'Uploading ' + file.name + '...';
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch('/api/wells/' + this.currentWell.id + '/production/upload-csv', {
                method: 'POST',
                body: formData,
                headers: this._authHeaders(),
            });
                const result = await resp.json();
                if (!resp.ok) throw new Error(result?.detail || 'Upload failed');
                if (status) status.textContent = 'Inserted ' + (result.inserted || 0) + ' rows';
                GeoToast.success('Production CSV uploaded');
                await this.loadProduction();
            } catch (e) {
                if (status) status.textContent = 'Upload failed';
                GeoToast.error('Production CSV upload failed: ' + (e.message || e));
            } finally {
                input.value = '';
            }
        });
    },

    async openTrajectoryEditor() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const r = await GeoModal.show({ title: 'Deviation Survey', fields: [
            { id: 'data', label: 'Paste MD,INC,AZI (one per line)', type: 'text', placeholder: '0,0,0\n100,2,45\n200,5,90\n...' },
        ]});
        if (!r?.data) return;
        const lines = r.data.split('\n').filter(l => l.trim());
        const points = [];
        for (const line of lines) {
            const parts = line.split(',').map(v => parseFloat(v.trim()));
            if (parts.length >= 3 && !isNaN(parts[0])) {
                points.push({ md: parts[0], inc: parts[1], azi: parts[2] });
            }
        }
        if (points.length < 2) return GeoToast.warn('Need at least 2 survey points');
        GeoLoading.show('Computing TVD (minimum curvature)...');
        try {
            const result = await this._api('/wells/' + this.currentWell.id + '/trajectory', {
                method: 'POST', body: JSON.stringify({ points }),
            });
            GeoToast.success('Trajectory saved: ' + result.points + ' points, TVD ' + result.tvd_range[0] + '-' + result.tvd_range[1]);
            const status = document.getElementById('trajectoryStatus');
            if (status) status.textContent = result.points + ' pts, TVD ' + result.tvd_range[0] + '-' + result.tvd_range[1] + ' ft';
        } catch (e) { GeoToast.error('Trajectory failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    },

    async viewTrajectory() {
        if (!this.currentWell) return;
        try {
            const data = await this._api('/wells/' + this.currentWell.id + '/trajectory');
            if (!data.points?.length) { GeoToast.info('No trajectory data'); return; }
            const panel = document.getElementById('trajectoryStatus');
            if (panel) panel.textContent = data.points.length + ' pts, TVD range: ' + data.points[0].tvd + '-' + data.points[data.points.length - 1].tvd + ' ft';
            GeoToast.info('Trajectory loaded: ' + data.points.length + ' points');
        } catch { GeoToast.info('No trajectory data'); }
    },

    async loadDataTable() {
        if (!this.currentWell || !this.currentLogRun) return;
        const from = document.getElementById('dtFrom').value || '';
        const to = document.getElementById('dtTo').value || '';
        const limit = document.getElementById('dtLimit').value || 200;
        try {
            let url = `/wells/${this.currentWell.id}/data-table?limit=${limit}`;
            if (from) url += `&from_depth=${from}`;
            if (to) url += `&to_depth=${to}`;
            const data = await this._api(url);
            this._lastDataTable = data;
            const cols = data.columns;
            let html = `<div style="margin-bottom:8px;color:#8b949e;font-size:12px">Showing ${data.shown_points} of ${data.total_points} points</div>`;
            html += '<div style="overflow:auto;max-height:calc(100vh - 200px)"><table style="width:100%;border-collapse:collapse;font-size:11px;font-family:IBM Plex Mono,monospace">';
            html += '<thead><tr style="position:sticky;top:0;background:#161b22">';
            for (const c of cols) html += `<th style="border:1px solid #30363d;padding:4px 8px;color:#58a6ff;cursor:pointer" data-sort-curve="${escapeHtml(c)}">${escapeHtml(c)}</th>`;
            html += '</tr></thead><tbody>';
            for (const row of data.rows) {
                html += '<tr>';
                for (const v of row) {
                    const display = (v === null || v === undefined) ? '<span style="color:#484f58">-</span>' : (typeof v === 'number' ? v.toFixed(3) : v);
                    html += `<td style="border:1px solid #21262d;padding:3px 8px;color:#c9d1d9">${display}</td>`;
                }
                html += '</tr>';
            }
            html += '</tbody></table></div>';
            document.getElementById('dataTableContent').innerHTML = html;
        } catch (e) { GeoToast.error(e.message); }
    },

    _sortDataTable(col) {
        if (!this._lastDataTable) return;
        const idx = this._lastDataTable.columns.indexOf(col);
        if (idx < 0) return;
        this._lastDataTable.rows.sort((a, b) => {
            const va = a[idx], vb = b[idx];
            if (va === null && vb === null) return 0;
            if (va === null) return 1;
            if (vb === null) return -1;
            return va - vb;
        });
        this.loadDataTable(); // re-render with sorted data (uses _lastDataTable)
        // Actually, let's just re-render from cached data
        const data = this._lastDataTable;
        const cols = data.columns;
        let html = `<div style="margin-bottom:8px;color:#8b949e;font-size:12px">Showing ${data.shown_points} of ${data.total_points} points (sorted by ${col})</div>`;
        html += '<div style="overflow:auto;max-height:calc(100vh - 200px)"><table style="width:100%;border-collapse:collapse;font-size:11px;font-family:IBM Plex Mono,monospace">';
        html += '<thead><tr style="position:sticky;top:0;background:#161b22">';
        for (const c of cols) html += `<th style="border:1px solid #30363d;padding:4px 8px;color:#58a6ff;cursor:pointer" data-sort-curve="${escapeHtml(c)}">${escapeHtml(c)}</th>`;
        html += '</tr></thead><tbody>';
        for (const row of data.rows) {
            html += '<tr>';
            for (const v of row) {
                const display = (v === null || v === undefined) ? '<span style="color:#484f58">-</span>' : (typeof v === 'number' ? v.toFixed(3) : v);
                html += `<td style="border:1px solid #21262d;padding:3px 8px;color:#c9d1d9">${display}</td>`;
            }
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        document.getElementById('dataTableContent').innerHTML = html;
    },

    exportDataTableCSV() {
        if (!this._lastDataTable) { GeoToast.warning('Load data first'); return; }
        const data = this._lastDataTable;
        let csv = data.columns.join(',') + '\n';
        for (const row of data.rows) csv += row.map(v => v === null ? '' : v).join(',') + '\n';
        const blob = new Blob([csv], { type: 'text/csv' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = `${this.currentWell?.name || 'data'}_table.csv`; a.click();
    },

    _renderTopsManagement() {
        if (!this.currentWell) return;
        const tops = this.formationTops || [];
        let html = '<div style="overflow:auto">';
        html += '<table style="width:100%;border-collapse:collapse;font-size:12px">';
        html += '<thead><tr style="background:#161b22">';
        html += '<th style="padding:6px;border:1px solid #30363d;color:#58a6ff">Formation</th>';
        html += '<th style="padding:6px;border:1px solid #30363d;color:#58a6ff">Depth</th>';
        html += '<th style="padding:6px;border:1px solid #30363d;color:#58a6ff">Top</th>';
        html += '<th style="padding:6px;border:1px solid #30363d;color:#58a6ff">Base</th>';
        html += '<th style="padding:6px;border:1px solid #30363d;color:#58a6ff">Color</th>';
        html += '<th style="padding:6px;border:1px solid #30363d;color:#58a6ff">Lithology</th>';
        html += '<th style="padding:6px;border:1px solid #30363d;color:#58a6ff">Actions</th>';
        html += '</tr></thead><tbody>';
        for (const t of tops) {
            html += `<tr>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${escapeHtml(t.formation_name)}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${t.depth.toFixed(1)}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${t.top_depth?.toFixed(1) ?? '-'}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${t.base_depth?.toFixed(1) ?? '-'}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d"><span style="display:inline-block;width:16px;height:16px;border-radius:3px;background:${t.color}"></span></td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${escapeHtml(t.lithology || '-')}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d">`;
            html += `<button class="btn-sm" data-action="app.editFormationTop" data-args='[${t.id}]' style="font-size:10px">✏️</button> `;
            html += `<button class="btn-sm" data-action="app.deleteFormationTop" data-args='[${t.id}]' style="font-size:10px;color:#f85149">🗑️</button>`;
            html += '</td></tr>';
        }
        html += '</tbody></table></div>';
        if (!tops.length) html = '<p style="color:#8b949e">No formation tops. Add one from the viewer toolbar or import CSV.</p>';
        document.getElementById('topsMgmtContent').innerHTML = html;
    },

    async exportTopsCSV() {
        if (!this.projects?.[0]) return;
        const pid = this.projects[0].id;
        try {
            const resp = await fetch(`/api/projects/${pid}/tops-export`, { headers: this._authHeaders() });
            const text = await resp.text();
            const blob = new Blob([text], { type: 'text/csv' });
            const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
            a.download = `tops_project_${pid}.csv`; a.click();
            GeoToast.success('Tops exported');
        } catch (e) { GeoToast.error(e.message); }
    },

    async exportTopsPetrel() {
        if (!this.currentWell) return;
        try {
            const resp = await fetch(`/api/wells/${this.currentWell.id}/tops-petrel`, { headers: this._authHeaders() });
            const text = await resp.text();
            const blob = new Blob([text], { type: 'text/csv' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `tops_petrel_${this.currentWell.name}.csv`;
            a.click();
            GeoToast.success('Petrel-format tops exported');
        } catch (e) { GeoToast.error(e.message); }
    },

    async importTopsCSV() {
        if (!this.currentWell) { GeoToast.warning('Select a well first'); return; }
        const input = document.createElement('input');
        input.type = 'file'; input.accept = '.csv';
        input.onchange = async () => {
            const file = input.files[0]; if (!file) return;
            const text = await file.text();
            try {
                const result = await this._api(`/wells/${this.currentWell.id}/tops-import`, {
                    method: 'POST', body: JSON.stringify({ csv_data: text })
                });
                GeoToast.success(`Imported ${result.imported} tops, ${result.skipped} skipped`);
                this.formationTops = await this._api(`/wells/${this.currentWell.id}/tops`);
                this._renderTopsManagement();
                if (this.renderer) this.renderer.formationTops = this.formationTops;
            } catch (e) { GeoToast.error(e.message); }
        };
        input.click();
    },

    async deleteFormationTop(id) {
        if (!confirm('Delete this formation top?')) return;
        try {
            await this._api(`/tops/${id}`, { method: 'DELETE' });
            this.formationTops = await this._api(`/wells/${this.currentWell.id}/tops`);
            this._renderTopsManagement();
            if (this.renderer) this.renderer.formationTops = this.formationTops;
            GeoToast.success('Top deleted');
        } catch (e) { GeoToast.error(e.message); }
    },

    async uploadLASForWell(wid) {
        return this._uploadLogFormatForWell(wid, 'las');
    },

    async uploadDLISForWell(wid) {
        return this._uploadLogFormatForWell(wid, 'dlis');
    },

    async uploadLISForWell(wid) {
        return this._uploadLogFormatForWell(wid, 'lis');
    },

    deleteWell(wid) {
        if (!confirm('Delete this well and all its data?')) return;
        fetch(`/api/wells/${wid}`, { method: 'DELETE', headers: this._authHeaders() }).then(() => {
            GeoToast.success('Well deleted');
            this.loadProjects();
        });
    },
});
