/**
 * GeoLog — Oil & Gas Well Log Viewer Application
 */

// ─── UI Utilities ────────────────────────────────────────────
const GeoModal = {
    _resolve: null,
    _confirmed: false,
    show({ title, fields, onConfirm }) {
        return new Promise(resolve => {
            this._resolve = resolve;
            this._confirmed = false;
            document.getElementById('modalTitle').textContent = title;
            const body = document.getElementById('modalBody');
            body.innerHTML = fields.map(f => {
                if (f.type === 'select') {
                    const opts = f.options.map(o => `<option value="${o.value}" ${o.value === f.value ? 'selected' : ''}>${o.label}</option>`).join('');
                    return `<label>${f.label}</label><select id="m_${f.id}">${opts}</select>`;
                }
                return `<label>${f.label}</label><input id="m_${f.id}" type="${f.type || 'text'}" value="${f.value ?? ''}" placeholder="${f.placeholder || ''}"${f.step ? ` step="${f.step}"` : ''}${f.type === 'color' ? ' style="height:36px;padding:2px 4px"' : ''}>`;
            }).join('');
            const footer = document.getElementById('modalFooter');
            footer.innerHTML = `<button onclick="GeoModal.close()">Cancel</button><button class="btn-primary" id="modalConfirm">OK</button>`;
            document.getElementById('modalConfirm').onclick = () => {
                const result = {};
                fields.forEach(f => { result[f.id] = document.getElementById(`m_${f.id}`).value; });
                this._confirmed = true;
                this._hide();
                if (onConfirm) onConfirm(result);
                resolve(result);
            };
            document.getElementById('modalOverlay').style.display = 'flex';
            setTimeout(() => { const first = body.querySelector('input, select'); if (first) first.focus(); }, 100);
        });
    },
    _hide() {
        document.getElementById('modalOverlay').style.display = 'none';
        this._resolve = null;
    },
    close() {
        if (this._resolve) { const r = this._resolve; this._resolve = null; r(null); }
        this._hide();
    }
};

const GeoToast = {
    show(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icons = { success: '✓', error: '✕', info: 'ℹ', warn: '⚠' };
        toast.innerHTML = `<span>${icons[type] || ''}</span><span>${message}</span>`;
        container.appendChild(toast);
        setTimeout(() => { toast.classList.add('fade-out'); setTimeout(() => toast.remove(), 300); }, duration);
    },
    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 5000); },
    info(msg) { this.show(msg, 'info'); },
    warn(msg) { this.show(msg, 'warn', 4000); }
};

const GeoLoading = {
    show(text = 'Loading...') {
        document.getElementById('loadingText').textContent = text;
        document.getElementById('loadingOverlay').style.display = 'flex';
    },
    hide() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
};

class GeoLogApp {
    constructor() {
        this.renderer = null;
        this.currentWell = null;
        this.currentLogRun = null;
        this.curveConfig = {};
        this.wells = [];
        this.projects = [];
        this.corrMarkers = [];
        this.corrPickMode = false;
        this.corrLastRender = null;
        this._corrLoadedKey = null;
        this._corrTopCache = { a: [], b: [] };
        this._petroCache = null;
        this.zoneUndoStack = [];
        this.zoneRedoStack = [];

        this.init();
    }

    async init() {
        this.renderer = new LogRenderer('logCanvas');
        this._bindUI();
        await this.loadCurveConfig();
        await this.loadProjects();
        const lastWell = localStorage.getItem('geolog_last_well');
        if (lastWell && this.wells.find(w => w.id === parseInt(lastWell))) {
            await this.selectWell(parseInt(lastWell));
            const lastRun = localStorage.getItem('geolog_last_run');
            if (lastRun && this.currentWell?.log_runs?.find(r => r.id === parseInt(lastRun))) {
                await this.selectLogRun(parseInt(lastRun));
            }
        }
        if (typeof lucide !== 'undefined') lucide.createIcons();
        this._showFirstRunWelcome();
        this._bindContextMenu();
    }

    _bindUI() {
        // Navigation
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchView(btn.dataset.view));
        });

        // Scale selector
        const scaleSelect = document.getElementById('scaleSelect');
        if (scaleSelect) {
            scaleSelect.addEventListener('change', () => {
                const scale = parseInt(scaleSelect.value);
                this.renderer.scale = scale;
                this._loadCurveData();
            });
        }

        // Depth inputs
        const topInput = document.getElementById('depthTop');
        const bottomInput = document.getElementById('depthBottom');
        if (topInput && bottomInput) {
            const applyDepth = () => {
                const start = parseFloat(topInput.value);
                const stop = parseFloat(bottomInput.value);
                if (!isNaN(start) && !isNaN(stop) && stop > start) {
                    this.renderer.setView(start, stop);
                }
            };
            topInput.addEventListener('change', applyDepth);
            bottomInput.addEventListener('change', applyDepth);
        }

        // Search
        const searchInput = document.getElementById('wellSearch');
        if (searchInput) {
            searchInput.addEventListener('input', () => this._filterWells(searchInput.value));
        }

        // Export buttons
        document.getElementById('btnExportPNG')?.addEventListener('click', () => this.renderer?.exportPNG());
        document.getElementById('btnExportLAS')?.addEventListener('click', () => this._exportLAS());
        document.getElementById('btnHelp')?.addEventListener('click', () => this.openShortcutHelp());

        // Window resize
        window.addEventListener('resize', () => {
            if (this.renderer) {
                this.renderer._setupCanvas();
                this.renderer.render();
            }
        });

        // Log run selector
        document.getElementById('logRunSelect')?.addEventListener('change', (e) => {
            const id = parseInt(e.target.value || '0');
            if (id) this.selectLogRun(id);
        });

        // Correlation canvas pick handler
        document.getElementById('correlationCanvas')?.addEventListener('click', (ev) => this._onCorrelationCanvasClick(ev));
        document.getElementById('logCanvas')?.addEventListener('click', (e) => {
            if (!e.ctrlKey || !this.renderer || !this.currentWell) return;
            const canvas = document.getElementById('logCanvas');
            if (!canvas) return;
            const rect = canvas.getBoundingClientRect();
            const y = e.clientY - rect.top;
            const depth = this.renderer._yToDepth(y);
            if (!Number.isFinite(depth) || depth < 0) return;
            this.addFormationTopAtDepth(depth);
        });
        document.getElementById('corrWellA')?.addEventListener('change', () => { this._corrLoadedKey = null; this.renderCorrelation(); });
        document.getElementById('corrWellB')?.addEventListener('change', () => { this._corrLoadedKey = null; this.renderCorrelation(); });

        // Drag-and-drop LAS upload
        const dropZone = document.getElementById('logDropZone');
        if (dropZone) {
            dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.outline = '2px solid #58a6ff'; });
            dropZone.addEventListener('dragleave', () => { dropZone.style.outline = ''; });
            dropZone.addEventListener('drop', async (e) => {
                e.preventDefault();
                dropZone.style.outline = '';
                const file = e.dataTransfer?.files?.[0];
                if (!file || !file.name.toLowerCase().endsWith('.las')) {
                    GeoToast.warn('Drop a .las file');
                    return;
                }
                if (!this.currentWell) {
                    GeoToast.warn('Select or create a well first');
                    return;
                }
                const formData = new FormData();
                formData.append('file', file);
                try {
                    GeoLoading.show(`Uploading ${file.name}...`);
                    const resp = await fetch(`/api/wells/${this.currentWell.id}/upload-las`, { method: 'POST', body: formData });
                    if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
                    const result = await resp.json();
                    GeoToast.success(`Uploaded ${result.filename} — ${result.curves.length} curves, ${result.num_points} points`);
                    await this.loadWells(this.projects[0].id);
                } catch (err) {
                    GeoToast.error('Upload failed: ' + err.message);
                } finally {
                    GeoLoading.hide();
                }
            });
        }
    }

    // ─── Navigation ──────────────────────────────────────────
    switchView(view) {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelector(`.nav-btn[data-view="${view}"]`)?.classList.add('active');

        document.getElementById('viewerPanel').style.display = view === 'viewer' ? 'block' : 'none';
        document.getElementById('crossplotPanel').style.display = view === 'crossplot' ? 'block' : 'none';
        document.getElementById('pickettPanel').style.display = view === 'pickett' ? 'block' : 'none';
        document.getElementById('mnplotPanel').style.display = view === 'mnplot' ? 'block' : 'none';
        document.getElementById('petrophysicsPanel').style.display = view === 'petrophysics' ? 'block' : 'none';
        document.getElementById('qcPanel').style.display = view === 'qc' ? 'block' : 'none';
        document.getElementById('correlationPanel').style.display = view === 'correlation' ? 'block' : 'none';
        document.getElementById('statisticsPanel').style.display = view === 'statistics' ? 'block' : 'none';
        document.getElementById('sensitivityPanel').style.display = view === 'sensitivity' ? 'block' : 'none';
        document.getElementById('comparisonPanel').style.display = view === 'comparison' ? 'block' : 'none';
        document.getElementById('toolsPanel').style.display = view === 'tools' ? 'block' : 'none';
        document.getElementById('faciesPanel').style.display = view === 'facies' ? 'block' : 'none';
        document.getElementById('striplogPanel').style.display = view === 'striplog' ? 'block' : 'none';
        document.getElementById('probabilityPanel').style.display = view === 'probability' ? 'block' : 'none';
        document.getElementById('moveablePanel').style.display = view === 'moveable' ? 'block' : 'none';
        document.getElementById('dipplotPanel').style.display = view === 'dipplot' ? 'block' : 'none';
        document.getElementById('bucklesPanel').style.display = view === 'buckles' ? 'block' : 'none';
        document.getElementById('hinglePanel').style.display = view === 'hingle' ? 'block' : 'none';
        document.getElementById('calculatorPanel').style.display = view === 'calculator' ? 'block' : 'none';
        document.getElementById('datatablePanel').style.display = view === 'datatable' ? 'block' : 'none';
        document.getElementById('topsmgmtPanel').style.display = view === 'topsmgmt' ? 'block' : 'none';
        document.getElementById('formationPanel').style.display = view === 'formation' ? 'block' : 'none';
        document.getElementById('batchPanel').style.display = view === 'batch' ? 'block' : 'none';
        document.getElementById('mapPanel').style.display = view === 'map' ? 'block' : 'none';
        document.getElementById('dashboardPanel').style.display = view === 'dashboard' ? 'block' : 'none';
        document.getElementById('matrixPanel').style.display = view === 'matrix' ? 'block' : 'none';
        document.getElementById('auditPanel').style.display = view === 'audit' ? 'block' : 'none';

        // Sprint 26: Update status bar + trigger panel-specific loads
        this._updateStatusBar(view);
        if (view === 'matrix') this.loadCrossPlotMatrix();
        if (view === 'audit') this._renderAuditPanel();

        if (view === 'crossplot') this._renderCrossPlot();
        if (view === 'pickett') this._renderPickettPlot();
        if (view === 'mnplot') this._renderMNPlot();
        if (view === 'petrophysics') this._renderPetrophysics();
        if (view === 'qc') this._renderQC();
        if (view === 'correlation') {
            this._renderCorrelationMarkerTable();
            this.renderCorrelation();
        }
        if (view === 'statistics') this._renderStatistics();
        if (view === 'sensitivity') { /* auto-loads on click */ }
        if (view === 'comparison') this.loadWellComparison();
        if (view === 'tools') this._initToolsPanel();
        if (view === 'facies') this._initFaciesPanel();
        if (view === 'striplog') this.renderStripLog();
        if (view === 'probability') this.runProbabilityPlot();
        if (view === 'moveable') this.runMoveableOil();
        if (view === 'dipplot') this.runDipPlot();
        if (view === 'buckles') this.runBuckles();
        if (view === 'hingle') this.runHingle();
        if (view === 'calculator') { /* user fills form */ }
        if (view === 'datatable') this.loadDataTable();
        if (view === 'topsmgmt') this._renderTopsManagement();
        if (view === 'formation') this.loadFormationMatrix();
        if (view === 'batch') { /* user fills form */ }
        if (view === 'map') this.renderWellMap();
        if (view === 'dashboard') this.loadDashboard();
    }

    // ─── API ─────────────────────────────────────────────────
    async _api(path, opts = {}) {
        try {
            const resp = await fetch('/api' + path, {
                headers: { 'Content-Type': 'application/json', ...opts.headers },
                ...opts,
            });
            if (!resp.ok) {
                let detail = `API error: ${resp.status}`;
                try { const j = await resp.json(); if (j.detail) detail = j.detail; } catch {}
                throw new Error(detail);
            }
            if (resp.status === 204) return null;
            return resp.json();
        } catch (e) {
            if (e.message !== 'Failed to fetch') {
                GeoToast.error(e.message || 'Network error');
            } else {
                GeoToast.error('Cannot reach server — is it running?');
            }
            throw e;
        }
    }

    async loadCurveConfig() {
        try {
            this.curveConfig = await this._api('/curve-config');
        } catch { this.curveConfig = {}; }
    }

    async loadProjects() {
        try {
            this.projects = await this._api('/projects/');
            this._renderProjectTree();
            if (this.projects.length > 0) {
                await this.loadWells(this.projects[0].id);
            }
        } catch (e) { console.error('Failed to load projects:', e); }
    }

    async loadWells(projectId) {
        try {
            this.wells = await this._api(`/wells/?project_id=${projectId}`);
            this._renderWellList();
            this._populateCorrelationWellSelectors();
            if (this.wells.length > 0) {
                await this.selectWell(this.wells[0].id);
            }
        } catch (e) { console.error('Failed to load wells:', e); }
    }

    async selectWell(wellId) {
        try {
            GeoLoading.show('Loading well data...');
            const well = await this._api(`/wells/${wellId}`);
            this.currentWell = well;

            // Highlight in sidebar
            document.querySelectorAll('.well-item').forEach(el => el.classList.remove('active'));
            document.querySelector(`.well-item[data-id="${wellId}"]`)?.classList.add('active');

            this.loadPetroParams();
            this._initBulkUpload();
            this._initCSVUpload();
            if (well.log_runs && well.log_runs.length > 0) {
                this.currentLogRun = well.log_runs[0];
                this._populateLogRunSelector(well.log_runs, this.currentLogRun.id);
                await this._loadCurveData();
                await this._loadFormationTops();
                await this._loadZones();
            } else {
                this.currentLogRun = null;
                this._populateLogRunSelector([], null);
            }

            this._renderWellHeader(well);
            localStorage.setItem('geolog_last_well', wellId);
        } catch (e) { console.error('Failed to select well:', e); }
            finally { GeoLoading.hide(); }
    }

    async selectLogRun(logRunId) {
        if (!this.currentWell?.id) return;
        try {
            const well = await this._api(`/wells/${this.currentWell.id}`);
            this.currentWell = well;
            const chosen = (well.log_runs || []).find(r => r.id === logRunId);
            if (!chosen) return;
            this.currentLogRun = chosen;
            this._populateLogRunSelector(well.log_runs || [], chosen.id);
            await this._loadCurveData();
            await this._loadFormationTops();
            await this._loadZones();
            this._renderWellHeader(well);
            if (this.currentLogRun) localStorage.setItem('geolog_last_run', logRunId);
        } catch (e) { console.error('Failed to select log run:', e); }
    }

    _populateLogRunSelector(logRuns = [], selectedId = null) {
        const sel = document.getElementById('logRunSelect');
        if (!sel) return;
        if (!logRuns.length) {
            sel.innerHTML = '<option value="">No log run</option>';
            return;
        }
        sel.innerHTML = logRuns.map((r, idx) => {
            const runNo = r.run_number ?? (idx + 1);
            const file = r.filename || 'unknown.las';
            const pts = r.num_points ?? 0;
            return `<option value="${r.id}">Run ${runNo} • ${file} • ${pts} pts</option>`;
        }).join('');
        const chosen = selectedId || logRuns[0].id;
        sel.value = String(chosen);
    }

    async _loadCurveData() {
        if (!this.currentLogRun) return;

        try {
            const curves = await this._api(`/log-runs/${this.currentLogRun.id}/curves`);
            const mnemonics = curves.map(c => c.mnemonic);

            const topInput = document.getElementById('depthTop');
            const bottomInput = document.getElementById('depthBottom');
            const start = topInput ? parseFloat(topInput.value) : this.currentLogRun.start_depth;
            const stop = bottomInput ? parseFloat(bottomInput.value) : this.currentLogRun.stop_depth;

            const data = await this._api(`/log-runs/${this.currentLogRun.id}/data`, {
                method: 'POST',
                body: JSON.stringify({
                    curve_mnemonics: mnemonics,
                    start_depth: start,
                    stop_depth: stop,
                }),
            });

            const depth = data.DEPTH || [];
            const curveData = {};
            for (const c of curves) {
                if (data[c.mnemonic]) {
                    curveData[c.mnemonic] = data[c.mnemonic];
                }
            }

            // Update renderer
            this.renderer.setData(depth, curveData, this.formationTops, this.curveConfig);

            // Set scale
            const scale = parseInt(document.getElementById('scaleSelect')?.value || '100');
            this.renderer.scale = scale;

            // Update depth inputs
            if (topInput) topInput.value = start?.toFixed(1) || '';
            if (bottomInput) bottomInput.value = stop?.toFixed(1) || '';

            // Update curve panel
            this._renderCurvePanel(curves);
            this._populateCurveSelectors(curves);
        } catch (e) { console.error('Failed to load curve data:', e); }
    }

    async _loadFormationTops() {
        if (!this.currentWell) return;
        try {
            this.formationTops = await this._api(`/wells/${this.currentWell.id}/tops`);
            if (this.renderer) {
                this.renderer.formationTops = this.formationTops;
                this.renderer.render();
            }
            this._renderTopsList();
        } catch (e) { console.error('Failed to load formation tops:', e); }
    }

    async _loadZones() {
        if (!this.currentWell || !this.renderer) return;
        try {
            const rows = await this._api(`/wells/${this.currentWell.id}/zones`);
            const zones = (rows || []).map(z => ({
                id: z.id,
                name: z.name,
                top: Number(z.top_depth),
                bottom: Number(z.bottom_depth),
                color: z.color || '#1f6feb',
            })).filter(z => Number.isFinite(z.top) && Number.isFinite(z.bottom) && z.bottom > z.top);
            this.renderer.setZones(zones);
            this.zoneUndoStack = [];
            this.zoneRedoStack = [];
            this._renderZonesList();
        } catch (e) {
            console.error('Failed to load zones:', e);
        }
    }

    async _saveZones() {
        if (!this.currentWell || !this.renderer) return;
        const payload = {
            zones: (this.renderer.zones || []).map(z => ({
                id: z.id,
                name: z.name,
                top: z.top,
                bottom: z.bottom,
                color: z.color || '#1f6feb',
            }))
        };
        await this._api(`/wells/${this.currentWell.id}/zones`, {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    }

    async _loadCorrelationProfile() {
        const { wellAId, wellBId } = this._currentCorrPair();
        if (!wellAId || !wellBId) return;
        try {
            const curve = document.getElementById('corrCurve')?.value || 'GR';
            const p = await this._api(`/correlation-profile?well_a_id=${wellAId}&well_b_id=${wellBId}&curve=${curve}`);
            const shiftInput = document.getElementById('corrShift');
            const stretchInput = document.getElementById('corrStretch');
            const snapInput = document.getElementById('corrSnapTops');
            if (shiftInput) shiftInput.value = (p.depth_shift ?? 0).toFixed(1);
            if (stretchInput) stretchInput.value = (p.stretch ?? 1).toFixed(3);
            if (snapInput) snapInput.checked = !!p.snap_to_tops;
        } catch (e) {
            console.error('Failed to load correlation profile:', e);
        }
    }

    async _saveCorrelationProfile() {
        const { wellAId, wellBId } = this._currentCorrPair();
        if (!wellAId || !wellBId) return;
        const curve = document.getElementById('corrCurve')?.value || 'GR';
        const shift = parseFloat(document.getElementById('corrShift')?.value || '0') || 0;
        const stretch = parseFloat(document.getElementById('corrStretch')?.value || '1') || 1;
        const snap = document.getElementById('corrSnapTops')?.checked ? 1 : 0;
        await this._api('/correlation-profile', {
            method: 'POST',
            body: JSON.stringify({ well_a_id: wellAId, well_b_id: wellBId, curve, depth_shift: shift, stretch, snap_to_tops: snap }),
        });
    }

    _pushZoneHistory() {
        if (!this.renderer) return;
        this.zoneUndoStack.push(JSON.parse(JSON.stringify(this.renderer.zones || [])));
        if (this.zoneUndoStack.length > 50) this.zoneUndoStack.shift();
        this.zoneRedoStack = [];
    }

    async undoZone() {
        if (!this.renderer || !this.zoneUndoStack.length) return GeoToast.warn('Nothing to undo');
        const current = JSON.parse(JSON.stringify(this.renderer.zones || []));
        this.zoneRedoStack.push(current);
        const prev = this.zoneUndoStack.pop();
        this.renderer.setZones(prev || []);
        this._renderZonesList();
        await this._saveZones();
        GeoToast.info('Zone undo applied');
    }

    async redoZone() {
        if (!this.renderer || !this.zoneRedoStack.length) return GeoToast.warn('Nothing to redo');
        const current = JSON.parse(JSON.stringify(this.renderer.zones || []));
        this.zoneUndoStack.push(current);
        const nxt = this.zoneRedoStack.pop();
        this.renderer.setZones(nxt || []);
        this._renderZonesList();
        await this._saveZones();
        GeoToast.info('Zone redo applied');
    }

    // ─── UI Rendering ────────────────────────────────────────
    _renderProjectTree() {
        const container = document.getElementById('projectTree');
        if (!container) return;
        container.innerHTML = this.projects.map(p => `
            <div class="project-group">
                <div class="project-header">
                    <span class="project-name">${p.name}</span>
                    <span class="project-meta">${p.operator || ''} • ${p.country || ''}</span>
                    <button class="btn-icon-sm" onclick="app.deleteProject(${p.id})" title="Delete">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
                <div class="well-list" id="wells-${p.id}"></div>
            </div>
        `).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    _renderWellList() {
        const container = document.querySelector('.well-list');
        if (!container) return;
        container.innerHTML = this.wells.map(w => `
            <div class="well-item" data-id="${w.id}" onclick="app.selectWell(${w.id})">
                <div class="well-name">${w.name}</div>
                <div class="well-meta">${w.uwi || '—'} • ${w.log_run_count || 0} logs</div>
            </div>
        `).join('');
    }

    _filterWells(query) {
        const items = document.querySelectorAll('.well-item');
        const q = query.toLowerCase();
        items.forEach(el => {
            const name = el.querySelector('.well-name')?.textContent.toLowerCase() || '';
            const meta = el.querySelector('.well-meta')?.textContent.toLowerCase() || '';
            el.style.display = (name.includes(q) || meta.includes(q)) ? 'block' : 'none';
        });
    }

    _populateCorrelationWellSelectors() {
        const a = document.getElementById('corrWellA');
        const b = document.getElementById('corrWellB');
        if (!a || !b) return;
        const opts = this.wells.map(w => `<option value="${w.id}">${w.name}</option>`).join('');
        a.innerHTML = opts;
        b.innerHTML = opts;
        if (this.wells.length > 0) a.value = String(this.wells[0].id);
        if (this.wells.length > 1) b.value = String(this.wells[1].id);
        else if (this.wells.length > 0) b.value = String(this.wells[0].id);
    }

    _currentCorrPair() {
        const wellAId = parseInt(document.getElementById('corrWellA')?.value || '0');
        const wellBId = parseInt(document.getElementById('corrWellB')?.value || '0');
        return { wellAId, wellBId };
    }

    async _loadCorrelationMarkers() {
        const { wellAId, wellBId } = this._currentCorrPair();
        if (!wellAId || !wellBId) return;
        try {
            this.corrMarkers = await this._api(`/correlation-markers?well_a_id=${wellAId}&well_b_id=${wellBId}`);
        } catch {
            this.corrMarkers = [];
        }
    }

    async _saveCorrelationMarkers() {
        const { wellAId, wellBId } = this._currentCorrPair();
        if (!wellAId || !wellBId) return;
        await this._api('/correlation-markers', {
            method: 'POST',
            body: JSON.stringify({ well_a_id: wellAId, well_b_id: wellBId, markers: this.corrMarkers || [] }),
        });
    }

    _curveFamilyLabel(mnemonic) {
        const m = (mnemonic || '').toUpperCase();
        if (['GR','SGR','CGR'].includes(m)) return 'GR-family';
        if (['RT','RESD','RILD','ILD','ILM','RILM','RLL3','RLLS','MSFL','RXO','SFLU','SFLA'].includes(m)) return 'RT-family';
        if (['NPHI','NPHI_LS'].includes(m)) return 'NPHI-family';
        if (['RHOB','RHOZ'].includes(m)) return 'RHOB-family';
        if (['DT','DTC','DTP','DTS'].includes(m)) return 'DT-family';
        if (['CAL','CALI','HCAL'].includes(m)) return 'CAL-family';
        return 'OTHER';
    }

    _populateCurveSelectors(curves = []) {
        const cpX = document.getElementById('cpCurveX');
        const cpY = document.getElementById('cpCurveY');
        const corr = document.getElementById('corrCurve');
        if (!cpX || !cpY || !corr) return;

        const uniqueMnemonics = [...new Set(curves.map(c => (c.mnemonic || '').toUpperCase()).filter(Boolean))];
        if (!uniqueMnemonics.length) return;

        const toOpt = (mn) => `<option value="${mn}">${mn} (${this._curveFamilyLabel(mn)})</option>`;
        const options = uniqueMnemonics.map(toOpt).join('');

        const keepX = cpX.value;
        const keepY = cpY.value;
        const keepC = corr.value;
        cpX.innerHTML = options;
        cpY.innerHTML = options;
        corr.innerHTML = options;

        cpX.value = uniqueMnemonics.includes(keepX) ? keepX : (uniqueMnemonics.includes('RHOB') ? 'RHOB' : uniqueMnemonics[0]);
        cpY.value = uniqueMnemonics.includes(keepY) ? keepY : (uniqueMnemonics.includes('NPHI') ? 'NPHI' : uniqueMnemonics[0]);
        corr.value = uniqueMnemonics.includes(keepC) ? keepC : (uniqueMnemonics.includes('GR') ? 'GR' : uniqueMnemonics[0]);
    }

    _activeLogRunForWell(well) {
        if (!well?.log_runs?.length) return null;
        if (this.currentWell?.id === well.id && this.currentLogRun) {
            const same = well.log_runs.find(r => r.id === this.currentLogRun.id);
            if (same) return same;
        }
        return well.log_runs[0];
    }

    async renderCorrelation() {
        const canvas = document.getElementById('correlationCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight || 500;

        const wellAId = parseInt(document.getElementById('corrWellA')?.value || '0');
        const wellBId = parseInt(document.getElementById('corrWellB')?.value || '0');
        const requestedCurve = document.getElementById('corrCurve')?.value || 'GR';
        const shift = parseFloat(document.getElementById('corrShift')?.value || '0');
        const stretch = parseFloat(document.getElementById('corrStretch')?.value || '1') || 1;
        const snapToTops = !!document.getElementById('corrSnapTops')?.checked;

        if (!wellAId || !wellBId) {
            ctx.fillStyle='#8b949e'; ctx.font='14px DM Sans'; ctx.fillText('Select wells', 40, 40); return;
        }

        const pairKey = `${wellAId}:${wellBId}`;
        if (this._corrLoadedKey !== pairKey) {
            await this._loadCorrelationMarkers();
            await this._loadCorrelationProfile();
            this._corrLoadedKey = pairKey;
        }

        const wa = await this._api(`/wells/${wellAId}`);
        const wb = await this._api(`/wells/${wellBId}`);
        const runA = this._activeLogRunForWell(wa);
        const runB = this._activeLogRunForWell(wb);
        if (!runA || !runB) {
            ctx.fillStyle='#8b949e'; ctx.font='14px DM Sans'; ctx.fillText('Both wells need log runs', 40, 40); return;
        }

        const da = await this._api(`/log-runs/${runA.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[requestedCurve], start_depth:runA.start_depth, stop_depth:runA.stop_depth})});
        const db = await this._api(`/log-runs/${runB.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[requestedCurve], start_depth:runB.start_depth, stop_depth:runB.stop_depth})});
        this._corrTopCache = {
            a: (wa.formation_tops || []).map(t => Number(t.top_depth ?? t.depth)).filter(v => Number.isFinite(v)).sort((x,y)=>x-y),
            b: (wb.formation_tops || []).map(t => Number(t.top_depth ?? t.depth)).filter(v => Number.isFinite(v)).sort((x,y)=>x-y),
        };

        let valsA = da[requestedCurve] || [];
        let valsB = db[requestedCurve] || [];
        let actualCurve = requestedCurve;

        if (!valsA.length || !valsB.length) {
            const fallbackFamilies = {
                RT: ['RT','RESD','RILD','ILD','ILM','RILM','RLL3','RLLS','MSFL','RXO','SFLU','SFLA'],
                GR: ['GR','SGR','CGR'],
                NPHI: ['NPHI','NPHI_LS'],
                RHOB: ['RHOB','RHOZ'],
            };
            const candidates = fallbackFamilies[requestedCurve] || [requestedCurve];
            for (const cand of candidates) {
                if (cand === requestedCurve) continue;
                const daCand = await this._api(`/log-runs/${runA.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[cand], start_depth:runA.start_depth, stop_depth:runA.stop_depth})});
                const dbCand = await this._api(`/log-runs/${runB.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[cand], start_depth:runB.start_depth, stop_depth:runB.stop_depth})});
                if ((daCand[cand] || []).length && (dbCand[cand] || []).length) {
                    valsA = daCand[cand];
                    valsB = dbCand[cand];
                    actualCurve = cand;
                    break;
                }
            }
        }

        const depthA = da.DEPTH || [];
        const rawDepthB = db.DEPTH || [];
        const midB = rawDepthB.length ? (rawDepthB[0] + rawDepthB[rawDepthB.length - 1]) / 2 : 0;
        let depthB = rawDepthB.map(d => (d - midB) * stretch + midB + shift);
        if (snapToTops && this._corrTopCache.a.length && this._corrTopCache.b.length) {
            depthB = this._applyTopSnapDepths(depthB, this._corrTopCache.a, this._corrTopCache.b, shift);
        }
        if (!depthA.length || !depthB.length) { ctx.fillStyle='#8b949e'; ctx.fillText('No data', 40, 40); return; }

        const xMin = Math.min(depthA[0], depthB[0]), xMax = Math.max(depthA[depthA.length-1], depthB[depthB.length-1]);
        const allVals = [...valsA.filter(v=>v!=null), ...valsB.filter(v=>v!=null)];
        let yMin = Infinity, yMax = -Infinity;
        for (const v of allVals) { if (v < yMin) yMin = v; if (v > yMax) yMax = v; }
        if (!isFinite(yMin)) { yMin = 0; yMax = 1; }

        const m={top:30,right:30,bottom:45,left:60}, w=canvas.width-m.left-m.right, h=canvas.height-m.top-m.bottom;
        const sx=v=>m.left+((v-xMin)/(xMax-xMin))*w;
        const sy=v=>m.top+h-((v-yMin)/(yMax-yMin))*h;

        ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,canvas.width,canvas.height);
        ctx.strokeStyle='#21262d'; for(let i=0;i<=8;i++){const x=m.left+w*i/8; ctx.beginPath(); ctx.moveTo(x,m.top); ctx.lineTo(x,m.top+h); ctx.stroke();}
        for(let i=0;i<=6;i++){const y=m.top+h*i/6; ctx.beginPath(); ctx.moveTo(m.left,y); ctx.lineTo(m.left+w,y); ctx.stroke();}

        const draw=(depth,val,color)=>{ ctx.strokeStyle=color; ctx.lineWidth=1.5; ctx.beginPath(); let st=false; for(let i=0;i<Math.min(depth.length,val.length);i++){ const v=val[i]; if(v==null||isNaN(v)) continue; const x=sx(depth[i]), y=sy(v); if(!st){ctx.moveTo(x,y); st=true;} else ctx.lineTo(x,y);} ctx.stroke(); };
        draw(depthA, valsA, '#58a6ff');
        draw(depthB, valsB, '#f85149');

        const corrActive = document.getElementById('corrActiveCurve');
        if (corrActive) {
            corrActive.textContent = actualCurve === requestedCurve
                ? `using ${actualCurve}`
                : `requested ${requestedCurve} -> using ${actualCurve}`;
        }

        ctx.fillStyle='#c9d1d9'; ctx.font='12px DM Sans'; ctx.fillText(`Correlation curve: ${actualCurve}`, m.left, 16);
        ctx.fillStyle='#58a6ff'; ctx.fillText(`A: ${wa.name}`, m.left+220, 16);
        ctx.fillStyle='#f85149'; ctx.fillText(`B: ${wb.name} (shift ${shift} ft)`, m.left+360, 16);
        ctx.fillStyle='#c9d1d9'; ctx.fillText('Depth', m.left+w/2, canvas.height-10);

        // Save render context for marker picking
        this.corrLastRender = { m, w, h, xMin, xMax, yMin, yMax, shift, stretch, midB, waName: wa.name, wbName: wb.name };

        // Draw marker ties
        this.corrMarkers.forEach((mk, idx) => {
            const xA = sx(mk.aDepth);
            const xB = sx(((mk.bDepth - midB) * stretch + midB + shift));
            const yTop = m.top + 10 + (idx % 6) * 16;
            ctx.strokeStyle = '#f2cc60';
            ctx.setLineDash([4,3]);
            ctx.beginPath(); ctx.moveTo(xA, m.top); ctx.lineTo(xA, m.top+h); ctx.stroke();
            ctx.strokeStyle = '#ff7b72';
            ctx.beginPath(); ctx.moveTo(xB, m.top); ctx.lineTo(xB, m.top+h); ctx.stroke();
            ctx.setLineDash([]);
            ctx.strokeStyle = '#8b949e';
            ctx.beginPath(); ctx.moveTo(xA, yTop); ctx.lineTo(xB, yTop); ctx.stroke();
            ctx.fillStyle = '#c9d1d9';
            ctx.font = '10px IBM Plex Mono';
            ctx.fillText(`M${idx+1} Δ=${(mk.aDepth - mk.bDepth).toFixed(1)}ft`, Math.min(xA,xB)+4, yTop-2);
        });

        this._renderCorrelationMarkerTable();
    }

    async autoTieShift() {
        const wellAId = parseInt(document.getElementById('corrWellA')?.value || '0');
        const wellBId = parseInt(document.getElementById('corrWellB')?.value || '0');
        const requestedCurve = document.getElementById('corrCurve')?.value || 'GR';
        const info = document.getElementById('corrInfo');
        if (!wellAId || !wellBId) return;

        const wa = await this._api(`/wells/${wellAId}`);
        const wb = await this._api(`/wells/${wellBId}`);
        const runA = this._activeLogRunForWell(wa);
        const runB = this._activeLogRunForWell(wb);
        if (!runA || !runB) return;

        const da = await this._api(`/log-runs/${runA.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[requestedCurve], start_depth:runA.start_depth, stop_depth:runA.stop_depth})});
        const db = await this._api(`/log-runs/${runB.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[requestedCurve], start_depth:runB.start_depth, stop_depth:runB.stop_depth})});

        let valsA = da[requestedCurve] || [];
        let valsB = db[requestedCurve] || [];
        let actualCurve = requestedCurve;
        if (!valsA.length || !valsB.length) {
            const fallbackFamilies = {
                RT: ['RT','RESD','RILD','ILD','ILM','RILM','RLL3','RLLS','MSFL','RXO','SFLU','SFLA'],
                GR: ['GR','SGR','CGR'],
                NPHI: ['NPHI','NPHI_LS'],
                RHOB: ['RHOB','RHOZ'],
            };
            const candidates = fallbackFamilies[requestedCurve] || [requestedCurve];
            for (const cand of candidates) {
                if (cand === requestedCurve) continue;
                const daCand = await this._api(`/log-runs/${runA.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[cand], start_depth:runA.start_depth, stop_depth:runA.stop_depth})});
                const dbCand = await this._api(`/log-runs/${runB.id}/data`, {method:'POST', body: JSON.stringify({curve_mnemonics:[cand], start_depth:runB.start_depth, stop_depth:runB.stop_depth})});
                if ((daCand[cand] || []).length && (dbCand[cand] || []).length) {
                    valsA = daCand[cand];
                    valsB = dbCand[cand];
                    actualCurve = cand;
                    break;
                }
            }
        }

        const depthA = da.DEPTH || [], depthB0 = db.DEPTH || [];
        if (!depthA.length || !depthB0.length || !valsA.length || !valsB.length) return;

        const mean = a => a.reduce((s,v)=>s+v,0)/a.length;
        const normalize = arr => {
            const v = arr.filter(x=>x!=null && !isNaN(x));
            if (!v.length) return arr;
            const m = mean(v); const sd = Math.sqrt(v.reduce((s,x)=>s+(x-m)**2,0)/v.length) || 1;
            return arr.map(x => (x==null||isNaN(x)) ? null : (x-m)/sd);
        };
        const aN = normalize(valsA), bN = normalize(valsB);

        const interpAt = (depths, vals, d) => {
            // nearest-neighbor for speed
            let lo=0, hi=depths.length-1;
            while (lo<hi){ const mid=(lo+hi)>>1; if (depths[mid]<d) lo=mid+1; else hi=mid; }
            const i = Math.max(0, Math.min(depths.length-1, lo));
            return vals[i];
        };

        let bestShift = 0, bestScore = -1e9;
        let bestPairs = 0;
        const minPairs = 30;
        for (let sh=-100; sh<=100; sh+=0.5) {
            let n=0, sxy=0;
            for (let i=0;i<depthA.length;i+=3) {
                const a = aN[i];
                if (a==null) continue;
                const b = interpAt(depthB0, bN, depthA[i]-sh);
                if (b==null) continue;
                sxy += a*b; n++;
            }
            if (n < minPairs) continue;
            const score = sxy/n;
            if (score > bestScore) { bestScore = score; bestShift = sh; bestPairs = n; }
        }

        const shiftInput = document.getElementById('corrShift');
        if (shiftInput) shiftInput.value = bestShift.toFixed(1);
        const corrActive = document.getElementById('corrActiveCurve');
        if (corrActive) {
            corrActive.textContent = actualCurve === requestedCurve
                ? `using ${actualCurve}`
                : `requested ${requestedCurve} -> using ${actualCurve}`;
        }
        if (info) {
            if (bestPairs < minPairs || !isFinite(bestScore) || bestScore < -1e8) {
                info.textContent = `AutoTie (${actualCurve}): low confidence (pairs<${minPairs}). Keep manual marker ties.`;
            } else {
                info.textContent = `AutoTie (${actualCurve}): shift ${bestShift.toFixed(1)} ft, score ${bestScore.toFixed(3)}, pairs ${bestPairs}`;
            }
        }
        await this.renderCorrelation();
    }

    _applyTopSnapDepths(depthB, topsA, topsB, shift) {
        if (!depthB.length || !topsA.length || !topsB.length) return depthB;
        const maxPairs = Math.min(topsA.length, topsB.length, 6);
        if (maxPairs < 2) return depthB;
        let biasSum = 0;
        let n = 0;
        for (let i = 0; i < maxPairs; i++) {
            const d = topsA[i] - (topsB[i] + shift);
            if (!Number.isFinite(d)) continue;
            biasSum += d;
            n += 1;
        }
        if (!n) return depthB;
        const bias = biasSum / n;
        return depthB.map(d => d + bias);
    }

    applyTopSnap() {
        const info = document.getElementById('corrInfo');
        if (!this._corrTopCache?.a?.length || !this._corrTopCache?.b?.length) {
            if (info) info.textContent = 'Top Snap skipped: missing tops on one/both wells';
            return;
        }
        const shiftInput = document.getElementById('corrShift');
        const shift = parseFloat(shiftInput?.value || '0') || 0;
        const maxPairs = Math.min(this._corrTopCache.a.length, this._corrTopCache.b.length, 6);
        let sumDelta = 0;
        let n = 0;
        for (let i = 0; i < maxPairs; i++) {
            const d = this._corrTopCache.a[i] - (this._corrTopCache.b[i] + shift);
            if (!Number.isFinite(d)) continue;
            sumDelta += d;
            n += 1;
        }
        if (!n) return;
        const extraShift = sumDelta / n;
        if (shiftInput) shiftInput.value = (shift + extraShift).toFixed(1);
        if (info) info.textContent = `Top Snap applied from ${n} top pairs: Δshift ${extraShift.toFixed(1)} ft`;
        this.renderCorrelation();
    }

    _normalizeTopName(name) {
        const raw = (name || '').toLowerCase();
        const synonyms = [
            [/\bformation\b/g, 'fm'],
            [/\bmember\b/g, 'mbr'],
            [/\btop\b/g, 'top'],
            [/\bbase\b/g, 'base'],
            [/\bupper\b/g, 'up'],
            [/\blower\b/g, 'lo'],
            [/\bmiddle\b/g, 'mid'],
            [/\bsandstone\b/g, 'sand'],
            [/\bshale\b/g, 'sh'],
            [/\blimestone\b/g, 'ls'],
            [/\bdolomite\b/g, 'dol'],
        ];
        let n = raw;
        synonyms.forEach(([re, rep]) => { n = n.replace(re, rep); });
        return n.replace(/[^a-z0-9]+/g, ' ').trim();
    }

    _tokenSet(s) {
        return new Set((s || '').split(' ').filter(Boolean));
    }

    _jaccard(a, b) {
        const sa = this._tokenSet(a);
        const sb = this._tokenSet(b);
        if (!sa.size || !sb.size) return 0;
        let inter = 0;
        sa.forEach(t => { if (sb.has(t)) inter += 1; });
        const uni = new Set([...sa, ...sb]).size;
        return uni ? inter / uni : 0;
    }

    _bestTopMatch(nameA, topsB) {
        let best = null;
        let bestScore = 0;
        for (const tb of topsB) {
            const score = this._jaccard(nameA, tb.n);
            if (score > bestScore) {
                bestScore = score;
                best = tb;
            }
        }
        return bestScore >= 0.5 ? { ...best, score: bestScore } : null;
    }

    applyTopNameTie() {
        const info = document.getElementById('corrInfo');
        const shiftInput = document.getElementById('corrShift');
        const waId = parseInt(document.getElementById('corrWellA')?.value || '0');
        const wbId = parseInt(document.getElementById('corrWellB')?.value || '0');
        const wa = this.wells.find(w => w.id === waId);
        const wb = this.wells.find(w => w.id === wbId);
        if (!wa || !wb) return;
        Promise.all([this._api(`/wells/${waId}`), this._api(`/wells/${wbId}`)]).then(([a, b]) => {
            const topsA = (a.formation_tops || []).map(t => ({ raw: t.formation_name || '', n: this._normalizeTopName(t.formation_name), d: Number(t.top_depth ?? t.depth) })).filter(x => x.n && Number.isFinite(x.d));
            const topsB = (b.formation_tops || []).map(t => ({ raw: t.formation_name || '', n: this._normalizeTopName(t.formation_name), d: Number(t.top_depth ?? t.depth) })).filter(x => x.n && Number.isFinite(x.d));

            const deltas = [];
            let exact = 0;
            let fuzzy = 0;
            topsA.forEach(t => {
                const exactHit = topsB.find(x => x.n === t.n);
                if (exactHit) {
                    deltas.push(t.d - exactHit.d);
                    exact += 1;
                    return;
                }
                const fuzzyHit = this._bestTopMatch(t.n, topsB);
                if (fuzzyHit) {
                    deltas.push(t.d - fuzzyHit.d);
                    fuzzy += 1;
                }
            });
            if (!deltas.length) {
                if (info) info.textContent = 'Name Tie skipped: no exact/fuzzy top matches';
                return;
            }
            deltas.sort((x,y)=>x-y);
            const mid = Math.floor(deltas.length/2);
            const med = deltas.length % 2 ? deltas[mid] : (deltas[mid-1] + deltas[mid]) / 2;
            if (shiftInput) shiftInput.value = med.toFixed(1);
            if (info) info.textContent = `Name Tie: ${deltas.length} matches (exact ${exact}, fuzzy ${fuzzy}), median shift ${med.toFixed(1)} ft`;
            this.renderCorrelation();
        }).catch(err => {
            if (info) info.textContent = `Name Tie error: ${err.message || err}`;
        });
    }

    async saveCorrelationSettings() {
        await this._saveCorrelationProfile();
        GeoToast.success('Correlation profile saved');
    }

    startMarkerPick() {
        this.corrPickMode = true;
        this._corrPickTemp = null;
        const info = document.getElementById('corrInfo');
        if (info) info.textContent = 'Pick mode: click depth for Well A, then click depth for Well B';
    }

    async clearMarkers() {
        this.corrMarkers = [];
        const info = document.getElementById('corrInfo');
        if (info) info.textContent = 'Markers cleared';
        this._renderCorrelationMarkerTable();
        await this._saveCorrelationMarkers();
        this.renderCorrelation();
    }

    _calcMarkerShift(method = 'median') {
        if (!this.corrMarkers.length) return null;
        const deltas = this.corrMarkers.map(m => m.aDepth - m.bDepth).sort((a,b) => a-b);
        if (method === 'mean') {
            return deltas.reduce((s, v) => s + v, 0) / deltas.length;
        }
        const mid = Math.floor(deltas.length / 2);
        return deltas.length % 2 ? deltas[mid] : (deltas[mid - 1] + deltas[mid]) / 2;
    }

    applyMarkerShift(method = 'median') {
        const shift = this._calcMarkerShift(method);
        const info = document.getElementById('corrInfo');
        if (shift == null) {
            if (info) info.textContent = 'No markers yet. Pick markers first.';
            return;
        }
        const shiftInput = document.getElementById('corrShift');
        if (shiftInput) shiftInput.value = shift.toFixed(1);
        if (info) info.textContent = `Applied ${method} marker shift: ${shift.toFixed(1)} ft`;
        this.renderCorrelation();
    }

    _renderCorrelationMarkerTable() {
        const el = document.getElementById('corrMarkerTable');
        if (!el) return;
        if (!this.corrMarkers.length) {
            el.innerHTML = '<p style="color:#8b949e">No marker ties yet. Use <b>Pick Marker</b> to add A/B depth ties.</p>';
            return;
        }

        const rows = this.corrMarkers.map((m, idx) => {
            const d = m.aDepth - m.bDepth;
            return `<div class="stats-row"><span>M${idx + 1}</span><span>A ${m.aDepth.toFixed(1)} ft</span><span>B ${m.bDepth.toFixed(1)} ft</span><span>Δ ${d.toFixed(1)} ft</span></div>`;
        }).join('');
        const median = this._calcMarkerShift('median');
        const mean = this._calcMarkerShift('mean');
        el.innerHTML = `
            <div class="stats-card">
                <h4>Manual Marker Ties (${this.corrMarkers.length})</h4>
                ${rows}
                <div class="stats-row"><strong>Median Δ</strong><strong>${median.toFixed(1)} ft</strong></div>
                <div class="stats-row"><strong>Mean Δ</strong><strong>${mean.toFixed(1)} ft</strong></div>
            </div>
        `;
    }

    _onCorrelationCanvasClick(ev) {
        if (!this.corrPickMode || !this.corrLastRender) return;
        const cv = document.getElementById('correlationCanvas');
        if (!cv) return;
        const rect = cv.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const { m, w, xMin, xMax, shift, stretch, midB } = this.corrLastRender;
        if (x < m.left || x > m.left + w) return;

        const depth = xMin + ((x - m.left) / w) * (xMax - xMin);
        const info = document.getElementById('corrInfo');

        if (this._corrPickTemp == null) {
            this._corrPickTemp = depth;
            if (info) info.textContent = `Marker A picked @ ${depth.toFixed(1)} ft. Now click marker B depth.`;
        } else {
            const aDepth = this._corrPickTemp;
            const bDepth = ((depth - shift - midB) / (stretch || 1)) + midB;
            this.corrMarkers.push({ aDepth, bDepth });
            this._corrPickTemp = null;
            const localShift = aDepth - bDepth;
            if (info) info.textContent = `Marker tie added. Local shift Δ=${localShift.toFixed(1)} ft`;
            this._saveCorrelationMarkers().catch(() => {});
            this.renderCorrelation();
        }
    }

    _renderWellHeader(well) {
        document.getElementById('wellName').textContent = well.name || 'Unknown Well';
        document.getElementById('wellInfo').textContent = [
            well.uwi, well.operator, well.depth_unit
        ].filter(Boolean).join(' • ');

        const statsEl = document.getElementById('wellStats');
        if (statsEl && this.currentLogRun) {
            const runNo = this.currentLogRun.run_number ?? 1;
            const file = this.currentLogRun.filename || 'unknown.las';
            const s = Number(this.currentLogRun.start_depth);
            const e = Number(this.currentLogRun.stop_depth);
            const hasDepth = Number.isFinite(s) && Number.isFinite(e);
            const dTop = hasDepth ? Math.min(s, e) : null;
            const dBase = hasDepth ? Math.max(s, e) : null;
            const depthText = hasDepth ? `${dTop.toFixed(2)}-${dBase.toFixed(2)}` : 'n/a';
            const stepAbs = Number.isFinite(Number(this.currentLogRun.step)) ? Math.abs(Number(this.currentLogRun.step)).toFixed(4) : 'n/a';
            statsEl.textContent = `Run ${runNo} • ${file} • ${this.currentLogRun.num_points} pts • ${depthText} ${well.depth_unit} • step ${stepAbs}`;
        }
    }

    _renderCurvePanel(curves) {
        const panel = document.getElementById('curvePanel');
        if (!panel) return;

        panel.innerHTML = curves.filter(c => c.mnemonic !== (this.currentLogRun?.curves_json ? JSON.parse(this.currentLogRun.curves_json)[0]?.mnemonic : 'DEPT')).map(c => {
            const cfg = this.curveConfig[c.mnemonic] || {};
            const color = cfg.color || '#58a6ff';
            const track = cfg.track || '?';
            return `
                <div class="curve-row">
                    <span class="curve-dot" style="background:${color}"></span>
                    <span class="curve-name">${c.mnemonic}</span>
                    <span class="curve-unit">${c.unit || ''}</span>
                    <span class="curve-track">T${track}</span>
                    <span class="curve-range">${c.min_value?.toFixed(2)} – ${c.max_value?.toFixed(2)}</span>
                </div>
            `;
        }).join('');
    }

    _renderTopsList() {
        const panel = document.getElementById('topsPanel');
        if (!panel) return;

        panel.innerHTML = this.formationTops.map(t => `
            <div class="top-row">
                <span class="top-color" style="background:${t.color}"></span>
                <span class="top-name">${t.formation_name}</span>
                <span class="top-depth">${t.depth?.toFixed(1)} ${t.depth_unit || 'FT'}</span>
                <span class="top-lith">${t.lithology || ''}</span>
                <button class="btn-icon-sm" onclick="app.editTop(${t.id})" title="Edit">
                    <i data-lucide="pencil"></i>
                </button>
                <button class="btn-icon-sm" onclick="app.deleteTop(${t.id})" title="Delete">
                    <i data-lucide="x"></i>
                </button>
            </div>
        `).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    // ─── Actions ─────────────────────────────────────────────
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
    }

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
    }

    async addWell() {
        if (!this.projects.length) return this.createProject();
        const r = await GeoModal.show({ title: 'Add Well', fields: [
            { id: 'name', label: 'Well Name', placeholder: 'e.g. MELANIE-1' },
            { id: 'uwi', label: 'UWI / API Number (optional)', placeholder: '42-123-45678' },
        ]});
        if (!r?.name) return;
        try {
            await this._api('/wells/', {
                method: 'POST',
                body: JSON.stringify({ name: r.name, uwi: r.uwi || '', project_id: this.projects[0].id }),
            });
            await this.loadWells(this.projects[0].id);
            GeoToast.success('Well added');
        } catch (e) { GeoToast.error('Failed to add well: ' + e.message); }
    }

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
    }

    async deleteTop(id) {
        try {
            await this._api(`/tops/${id}`, { method: 'DELETE' });
            await this._loadFormationTops();
        } catch (e) { GeoToast.error('Failed to delete top: ' + e.message); }
    }

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
    }

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
            await this._api(`/wells/${this.currentWell.id}/tops`, {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            await this._loadFormationTops();
        } catch (e) { GeoToast.error('Failed to add top: ' + e.message); }
    }

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
            await this._api(`/wells/${this.currentWell.id}/tops`, {
                method: 'POST',
                body: JSON.stringify({
                    formation_name: result.name,
                    depth,
                    color: result.color || '#3fb950',
                    lithology: result.lithology || '',
                    depth_unit: 'FT'
                })
            });
            await this._loadFormationTops();
            GeoToast.success(`Top '${result.name}' added at ${depth.toFixed(1)} ft`);
        } catch (e) { GeoToast.error(e.message); }
    }

    async editCurrentWell() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const r = await GeoModal.show({ title: 'Edit Well', fields: [
            { id: 'name', label: 'Well Name', value: this.currentWell.name || '' },
            { id: 'uwi', label: 'UWI / API Number', value: this.currentWell.uwi || '' },
            { id: 'operator', label: 'Operator', value: this.currentWell.operator || '' },
            { id: 'field_name', label: 'Field Name', value: this.currentWell.field_name || '' },
            { id: 'depth_unit', label: 'Depth Unit', type: 'select', value: this.currentWell.depth_unit || 'FT', options: [{value:'FT',label:'Feet (FT)'},{value:'M',label:'Meters (M)'}] },
        ]});
        if (!r?.name) return;
        try {
            await this._api(`/wells/${this.currentWell.id}`, {
                method: 'PUT',
                body: JSON.stringify({ name: r.name, uwi: r.uwi, operator: r.operator, field_name: r.field_name, depth_unit: r.depth_unit }),
            });
            await this.loadWells(this.projects[0].id);
            GeoToast.success('Well updated');
        } catch (e) { GeoToast.error('Failed to update well: ' + e.message); }
    }

    async uploadLAS() {
        if (!this.currentWell) {
            GeoToast.warn('Select or create a well first.');
            return;
        }
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.las,.LAS';
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch(`/api/wells/${this.currentWell.id}/upload-las`, {
                    method: 'POST',
                    body: formData,
                });
                if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
                const result = await resp.json();
                GeoToast.success(`Uploaded ${result.filename} — ${result.curves.length} curves, ${result.num_points} points`);
                await this.loadWells(this.projects[0].id);
            } catch (e) { GeoToast.error('Upload failed: ' + e.message); }
        };
        input.click();
    }

    async uploadLASForWell(wellId) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.las,.LAS';
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch(`/api/wells/${wellId}/upload-las`, {
                    method: 'POST',
                    body: formData,
                });
                if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
                const result = await resp.json();
                GeoToast.success(`Uploaded ${result.filename} — ${result.curves.length} curves, ${result.num_points} points`);
                if (this.projects.length > 0) await this.loadWells(this.projects[0].id);
            } catch (e) { GeoToast.error('Upload failed: ' + e.message); }
        };
        input.click();
    }

    // ─── Export ──────────────────────────────────────────────
    _exportLAS() {
        if (!this.currentLogRun) { GeoToast.warn('No log run selected.'); return; }
        // Generate LAS content from current data
        const depth = this.renderer?.depthData;
        if (!depth || depth.length === 0) { GeoToast.warn('No data loaded.'); return; }

        let las = `~Version Information\n`;
        las += `VERS.   2.0 : CWLS Log ASCII Standard - VERSION 2.0\n`;
        las += `WRAP.   NO  : One line per depth step\n`;
        las += `~Well Information\n`;
        las += `STRT.${this.renderer.viewStart.toFixed(2)}\n`;
        las += `STOP.${this.renderer.viewStop.toFixed(2)}\n`;
        las += `STEP.0.1\n`;
        las += `NULL.-999.25\n`;
        las += `WELL.${this.currentWell?.name || 'Unknown'}\n`;
        las += `~Curve Information\n`;

        // Depth curve
        las += `DEPT.FT       : DEPTH\n`;

        // Curve definitions
        const curveNames = [];
        for (const track of this.renderer.tracks) {
            for (const mn of track.curves) {
                if (this.renderer.curveData[mn] && this.renderer.curveData[mn].length > 0) {
                    const cfg = this.curveConfig[mn] || {};
                    las += `${mn}.${cfg.unit || ''}       : ${cfg.name || mn}\n`;
                    curveNames.push(mn);
                }
            }
        }

        las += `~ASCII Data\n`;
        for (let i = 0; i < depth.length; i++) {
            let line = `${depth[i].toFixed(2)}`;
            for (const mn of curveNames) {
                const val = this.renderer.curveData[mn]?.[i];
                line += ` ${val !== null && val !== undefined ? val.toFixed(4) : '-999.25'}`;
            }
            las += line + '\n';
        }

        const blob = new Blob([las], { type: 'text/plain' });
        const link = document.createElement('a');
        link.download = `${this.currentWell?.name || 'export'}_${Date.now()}.las`;
        link.href = URL.createObjectURL(blob);
        link.click();
    }

    exportInterpretationSummary() {
        if (!this.renderer || !this.currentWell) return;

        const cutVsh = parseFloat(document.getElementById('cutVsh')?.value || '0.35');
        const cutPhie = parseFloat(document.getElementById('cutPhie')?.value || '0.10');
        const cutSw = parseFloat(document.getElementById('cutSw')?.value || '0.60');

        const depth = this.renderer.depthData || [];
        const vsh = this.renderer.curveData['VSH'] || [];
        const phie = this.renderer.curveData['PHIE'] || [];
        const sw = this.renderer.curveData['SW'] || [];
        const mdStep = Math.abs((depth[1] ?? 0) - (depth[0] ?? 0)) || 0;

        const pay = sw.map((_, i) => ((vsh[i] ?? 1) < cutVsh && (phie[i] ?? 0) > cutPhie && (sw[i] ?? 1) < cutSw) ? 1 : 0);
        let payCount = 0; pay.forEach(p => payCount += p);
        const gross = depth.length * mdStep;
        const netPay = payCount * mdStep;
        const ntg = gross > 0 ? netPay / gross : 0;

        const qcRows = [];
        for (const [mn, data] of Object.entries(this.renderer.curveData || {})) {
            if (mn === 'DEPT' || !Array.isArray(data)) continue;
            const total = data.length;
            const valid = data.filter(v => v !== null && v !== undefined && !isNaN(v));
            const missing = total - valid.length;
            const missPct = total ? (missing/total)*100 : 0;
            const mean = valid.length ? valid.reduce((s,v)=>s+v,0)/valid.length : 0;
            const std = valid.length ? Math.sqrt(valid.reduce((s,v)=>s+(v-mean)**2,0)/valid.length) : 0;
            let out = 0; for (const v of valid) if (std>0 && Math.abs((v-mean)/std)>3) out++;
            const outPct = valid.length ? (out/valid.length)*100 : 0;
            let tag = 'HIGH'; if (missPct>20 || outPct>8) tag='LOW'; else if (missPct>8 || outPct>4) tag='MEDIUM';
            qcRows.push([mn,total,valid.length,missPct.toFixed(2),outPct.toFixed(2),tag]);
        }

        const tops = this.formationTops || [];
        const lines = [];
        lines.push('section,key,value');
        lines.push(`well,name,${this.currentWell.name}`);
        lines.push(`well,uwi,${this.currentWell.uwi || ''}`);
        lines.push(`well,operator,${this.currentWell.operator || ''}`);
        lines.push(`cutoff,vsh_max,${cutVsh}`);
        lines.push(`cutoff,phie_min,${cutPhie}`);
        lines.push(`cutoff,sw_max,${cutSw}`);
        lines.push(`result,gross_ft,${gross.toFixed(2)}`);
        lines.push(`result,netpay_ft,${netPay.toFixed(2)}`);
        lines.push(`result,ntg_pct,${(ntg*100).toFixed(2)}`);

        lines.push('');
        lines.push('tops,formation,depth,lithology,color');
        tops.forEach(t => lines.push(`tops,${t.formation_name},${t.depth},${t.lithology || ''},${t.color || ''}`));

        lines.push('');
        lines.push('qc,curve,total,valid,missing_pct,outlier_pct,reliability');
        qcRows.forEach(r => lines.push(`qc,${r.join(',')}`));

        const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${this.currentWell.name || 'well'}_interpretation_summary.csv`;
        a.click();
    }

    // ─── Zone Picking ────────────────────────────────────────
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
        const zones = [...(this.renderer.zones || []), { name, top, bottom }];
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    }

    async removeZone(index) {
        this._pushZoneHistory();
        const zones = [...(this.renderer.zones || [])];
        zones.splice(index, 1);
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    }

    _renderZonesList() {
        const panel = document.getElementById('zonesPanel');
        if (!panel) return;
        const zones = this.renderer?.zones || [];
        const colors = this.renderer?.colors?.zoneColors || ['#1f6feb'];
        panel.innerHTML = zones.map((z, i) => `
            <div class="zone-row">
                <span class="zone-color" style="background:${z.color || colors[i % colors.length]}"></span>
                <span class="zone-name">${z.name}</span>
                <span class="zone-range">${z.top.toFixed(1)} – ${z.bottom.toFixed(1)}</span>
                <button class="btn-icon-sm" onclick="app.editZone(${i})" title="Edit">
                    <i data-lucide="pencil"></i>
                </button>
                <button class="btn-icon-sm" onclick="app.moveZoneUp(${i})" title="Move Up">
                    <i data-lucide="arrow-up"></i>
                </button>
                <button class="btn-icon-sm" onclick="app.moveZoneDown(${i})" title="Move Down">
                    <i data-lucide="arrow-down"></i>
                </button>
                <button class="btn-icon-sm" onclick="app.splitZone(${i})" title="Split">
                    <i data-lucide="split"></i>
                </button>
                <button class="btn-icon-sm" onclick="app.mergeZone(${i})" title="Merge Next">
                    <i data-lucide="merge"></i>
                </button>
                <button class="btn-icon-sm" onclick="app.removeZone(${i})" title="Remove">
                    <i data-lucide="x"></i>
                </button>
            </div>
        `).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

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
    }

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
    }

    async moveZoneUp(index) {
        const zones = [...(this.renderer.zones || [])];
        if (index <= 0 || index >= zones.length) return;
        this._pushZoneHistory();
        [zones[index - 1], zones[index]] = [zones[index], zones[index - 1]];
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    }

    async moveZoneDown(index) {
        const zones = [...(this.renderer.zones || [])];
        if (index < 0 || index >= zones.length - 1) return;
        this._pushZoneHistory();
        [zones[index], zones[index + 1]] = [zones[index + 1], zones[index]];
        this.renderer.setZones(zones);
        this._renderZonesList();
        await this._saveZones();
    }

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
    }

    _getCurveByFamily(family) {
        if (!this.renderer?.curveData) return null;
        const families = {
            RT: ['RT', 'RESD', 'RILD', 'ILD', 'ILM', 'RILM', 'RLL3', 'RLLS', 'MSFL', 'RXO', 'SFLU', 'SFLA'],
            NPHI: ['NPHI', 'NPHI_LS'],
            RHOB: ['RHOB', 'RHOZ'],
            DT: ['DT', 'DTC', 'DTP', 'DTS'],
            GR: ['GR', 'SGR', 'CGR'],
            CAL: ['CAL', 'CALI', 'HCAL'],
            DEPT: ['DEPT', 'DEPTH', 'MD', 'TVD'],
            PHIE: ['PHIE', 'NPHI'],
        };
        const keys = families[family] || [family];
        for (const k of keys) {
            const arr = this.renderer.curveData[k];
            if (Array.isArray(arr) && arr.length > 0) return { mnemonic: k, data: arr };
        }
        return null;
    }

    _curveOrFamily(selected, fallbackFamily = null) {
        const bySelected = this.renderer?.curveData?.[selected];
        if (Array.isArray(bySelected) && bySelected.length > 0) return { mnemonic: selected, data: bySelected, source: 'selected' };
        if (fallbackFamily) {
            const pack = this._getCurveByFamily(fallbackFamily);
            if (pack) return { ...pack, source: 'fallback' };
        }
        return null;
    }

    _setCurveResolutionHint(targetId, requested, pack) {
        const el = document.getElementById(targetId);
        if (!el) return;
        if (!pack) {
            el.textContent = `requested ${requested} -> no curve available`;
            return;
        }
        el.textContent = pack.source === 'selected'
            ? `using ${pack.mnemonic}`
            : `requested ${requested} -> using ${pack.mnemonic}`;
    }

    // ─── Cross Plot ──────────────────────────────────────────
    _renderCrossPlot() {
        const canvas = document.getElementById('crossplotCanvas');
        if (!canvas || !this.renderer) return;

        const ctx = canvas.getContext('2d');
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight || 500;

        const curveX = document.getElementById('cpCurveX')?.value || 'RHOB';
        const curveY = document.getElementById('cpCurveY')?.value || 'NPHI';

        const xPack = this._curveOrFamily(curveX, curveX);
        const yPack = this._curveOrFamily(curveY, curveY);
        this._setCurveResolutionHint('cpActiveX', curveX, xPack);
        this._setCurveResolutionHint('cpActiveY', curveY, yPack);
        const dataX = xPack?.data;
        const dataY = yPack?.data;
        if (!dataX || !dataY) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '14px DM Sans';
            ctx.textAlign = 'center';
            ctx.fillText('No data for selected/fallback curves', canvas.width / 2, canvas.height / 2);
            return;
        }

        // Build paired points
        const points = [];
        for (let i = 0; i < Math.min(dataX.length, dataY.length); i++) {
            if (dataX[i] !== null && dataY[i] !== null && !isNaN(dataX[i]) && !isNaN(dataY[i])) {
                points.push([dataX[i], dataY[i]]);
            }
        }

        if (points.length === 0) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '14px DM Sans';
            ctx.textAlign = 'center';
            ctx.fillText('No valid data points', canvas.width / 2, canvas.height / 2);
            return;
        }

        // Axes
        const margin = { top: 40, right: 40, bottom: 60, left: 70 };
        const plotW = canvas.width - margin.left - margin.right;
        const plotH = canvas.height - margin.top - margin.bottom;

        let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
        for (const p of points) {
            if (p[0] < xMin) xMin = p[0]; if (p[0] > xMax) xMax = p[0];
            if (p[1] < yMin) yMin = p[1]; if (p[1] > yMax) yMax = p[1];
        }

        // Background
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Grid
        ctx.strokeStyle = '#21262d';
        ctx.lineWidth = 0.5;
        for (let i = 0; i <= 5; i++) {
            const x = margin.left + (plotW * i / 5);
            const y = margin.top + (plotH * i / 5);
            ctx.beginPath();
            ctx.moveTo(x, margin.top);
            ctx.lineTo(x, margin.top + plotH);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(margin.left, y);
            ctx.lineTo(margin.left + plotW, y);
            ctx.stroke();
        }

        // Points
        ctx.fillStyle = '#58a6ff33';
        ctx.strokeStyle = '#58a6ff';
        ctx.lineWidth = 1;
        for (const [px, py] of points) {
            const x = margin.left + ((px - xMin) / (xMax - xMin)) * plotW;
            const y = margin.top + plotH - ((py - yMin) / (yMax - yMin)) * plotH;
            ctx.beginPath();
            ctx.arc(x, y, 2, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
        }

        // Axes labels
        ctx.fillStyle = '#c9d1d9';
        ctx.font = '12px DM Sans';
        ctx.textAlign = 'center';
        const xLabel = xPack?.mnemonic || curveX;
        const yLabel = yPack?.mnemonic || curveY;
        ctx.fillText(xLabel, margin.left + plotW / 2, canvas.height - 10);
        ctx.save();
        ctx.translate(15, margin.top + plotH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(yLabel, 0, 0);
        ctx.restore();

        // Axis values
        ctx.font = '10px IBM Plex Mono';
        ctx.textAlign = 'center';
        for (let i = 0; i <= 5; i++) {
            const xVal = xMin + (xMax - xMin) * i / 5;
            const yVal = yMin + (yMax - yMin) * i / 5;
            ctx.fillText(xVal.toFixed(2), margin.left + (plotW * i / 5), margin.top + plotH + 18);
            ctx.textAlign = 'right';
            ctx.fillText(yVal.toFixed(2), margin.left - 5, margin.top + plotH - (plotH * i / 5) + 4);
            ctx.textAlign = 'center';
        }

        // Point count + confidence
        ctx.fillStyle = '#8b949e';
        ctx.font = '11px DM Sans';
        ctx.textAlign = 'right';
        const conf = points.length < 30 ? 'LOW CONFIDENCE' : 'OK';
        ctx.fillText(`${points.length} points • ${conf}`, canvas.width - margin.right, margin.top - 10);
    }

    // ─── Pickett Plot ────────────────────────────────────────
    _renderPickettPlot() {
        const canvas = document.getElementById('pickettCanvas');
        if (!canvas || !this.renderer) return;

        const ctx = canvas.getContext('2d');
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight || 500;

        const rtPack = this._getCurveByFamily('RT');
        const phiePack = this._getCurveByFamily('PHIE');
        const rt = rtPack?.data;
        const phie = phiePack?.data;
        if (!rt || !phie) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '14px DM Sans';
            ctx.textAlign = 'center';
            ctx.fillText('Need resistivity + PHIE/NPHI curves for Pickett plot', canvas.width / 2, canvas.height / 2);
            return;
        }

        const pts = [];
        for (let i = 0; i < Math.min(rt.length, phie.length); i++) {
            const r = rt[i], p = phie[i];
            if (r && p && r > 0.2 && p > 0.01 && p < 0.5) pts.push([p, r]);
        }
        if (!pts.length) return;

        const margin = { top: 30, right: 30, bottom: 55, left: 70 };
        const w = canvas.width - margin.left - margin.right;
        const h = canvas.height - margin.top - margin.bottom;

        const xMin = 0.02, xMax = 0.4; // PHIE
        const yMin = 0.2, yMax = 2000; // RT
        const lx = v => (Math.log10(v) - Math.log10(xMin)) / (Math.log10(xMax) - Math.log10(xMin));
        const ly = v => (Math.log10(v) - Math.log10(yMin)) / (Math.log10(yMax) - Math.log10(yMin));

        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Log grid (decades)
        ctx.strokeStyle = '#21262d';
        ctx.lineWidth = 0.7;
        const xTicks = [0.02,0.03,0.05,0.07,0.1,0.15,0.2,0.3,0.4];
        const yTicks = [0.2,0.5,1,2,5,10,20,50,100,200,500,1000,2000];
        xTicks.forEach(t => {
            const x = margin.left + lx(t)*w;
            ctx.beginPath(); ctx.moveTo(x, margin.top); ctx.lineTo(x, margin.top+h); ctx.stroke();
        });
        yTicks.forEach(t => {
            const y = margin.top + h - ly(t)*h;
            ctx.beginPath(); ctx.moveTo(margin.left, y); ctx.lineTo(margin.left+w, y); ctx.stroke();
        });

        // Scatter
        ctx.fillStyle = '#58a6ff55';
        ctx.strokeStyle = '#58a6ff';
        pts.forEach(([p,r]) => {
            const x = margin.left + lx(p)*w;
            const y = margin.top + h - ly(r)*h;
            ctx.beginPath(); ctx.arc(x,y,2,0,Math.PI*2); ctx.fill();
        });

        // Archie Sw lines (quicklook)
        const a = parseFloat(document.getElementById('archA')?.value || '1');
        const m = parseFloat(document.getElementById('archM')?.value || '2');
        const n = parseFloat(document.getElementById('archN')?.value || '2');
        const rw = parseFloat(document.getElementById('archRw')?.value || '0.1');
        const swLines = [1.0, 0.7, 0.5, 0.3];
        swLines.forEach((sw, idx) => {
            ctx.strokeStyle = ['#f2cc60','#ffa657','#ff7b72','#a371f7'][idx];
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            let started = false;
            for (let p = xMin; p <= xMax; p += 0.002) {
                const rtCalc = a * rw / (Math.pow(p, m) * Math.pow(sw, n));
                if (rtCalc < yMin || rtCalc > yMax) continue;
                const x = margin.left + lx(p)*w;
                const y = margin.top + h - ly(rtCalc)*h;
                if (!started) { ctx.moveTo(x,y); started = true; } else ctx.lineTo(x,y);
            }
            ctx.stroke();
        });

        // Axes labels
        ctx.fillStyle = '#c9d1d9';
        ctx.font = '12px DM Sans';
        ctx.textAlign = 'center';
        ctx.fillText('PHIE (v/v) — log scale', margin.left + w/2, canvas.height - 14);
        ctx.save(); ctx.translate(18, margin.top + h/2); ctx.rotate(-Math.PI/2); ctx.fillText('RT (ohm·m) — log scale',0,0); ctx.restore();

        // Tick labels
        ctx.font = '10px IBM Plex Mono';
        ctx.fillStyle = '#8b949e';
        xTicks.forEach(t => {
            const x = margin.left + lx(t)*w;
            ctx.fillText(String(t), x, margin.top+h+14);
        });
        ctx.textAlign = 'right';
        yTicks.forEach(t => {
            const y = margin.top + h - ly(t)*h;
            ctx.fillText(String(t), margin.left-6, y+3);
        });
    }

    // ─── M-N Plot ───────────────────────────────────────────
    _renderMNPlot() {
        const canvas = document.getElementById('mnplotCanvas');
        if (!canvas || !this.renderer) return;
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight || 500;

        const nphiPack = this._getCurveByFamily('NPHI');
        const rhobPack = this._getCurveByFamily('RHOB');
        const dtPack = this._getCurveByFamily('DT');
        const nphi = nphiPack?.data;
        const rhob = rhobPack?.data;
        const dt = dtPack?.data;
        if (!nphi || !rhob || !dt) {
            ctx.fillStyle = '#8b949e'; ctx.font = '14px DM Sans'; ctx.textAlign = 'center';
            ctx.fillText('Need NPHI-family + RHOB-family + DT-family for M-N plot', canvas.width/2, canvas.height/2);
            return;
        }

        // Schlumberger-style M,N transforms (quicklook)
        // M = (Δt_f - Δt) / (ρb - ρf)
        // N = (φN_f - φN) / (ρb - ρf)
        const dtf = 189.0, rhof = 1.0, nphif = 1.0;
        const pts = [];
        for (let i=0;i<Math.min(nphi.length,rhob.length,dt.length);i++) {
            const p=nphi[i], r=rhob[i], t=dt[i];
            const den = (r - rhof);
            if (p==null || r==null || t==null || Math.abs(den)<0.05) continue;
            const M = (dtf - t)/den;
            const N = (nphif - p)/den;
            if (isFinite(M) && isFinite(N) && M>0 && M<200 && N>0 && N<2) pts.push([N,M]);
        }
        if (!pts.length) return;

        const margin={top:28,right:26,bottom:50,left:62};
        const w=canvas.width-margin.left-margin.right;
        const h=canvas.height-margin.top-margin.bottom;
        const xMin=0, xMax=1.2, yMin=0, yMax=140;
        const sx=v=>margin.left+((v-xMin)/(xMax-xMin))*w;
        const sy=v=>margin.top+h-((v-yMin)/(yMax-yMin))*h;

        ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,canvas.width,canvas.height);
        ctx.strokeStyle='#21262d'; ctx.lineWidth=0.6;
        for(let i=0;i<=6;i++){ const x=margin.left+(w*i/6); ctx.beginPath(); ctx.moveTo(x,margin.top); ctx.lineTo(x,margin.top+h); ctx.stroke(); }
        for(let i=0;i<=7;i++){ const y=margin.top+(h*i/7); ctx.beginPath(); ctx.moveTo(margin.left,y); ctx.lineTo(margin.left+w,y); ctx.stroke(); }

        // Data cloud
        ctx.fillStyle='#58a6ff55';
        for (const [N,M] of pts){ ctx.beginPath(); ctx.arc(sx(N),sy(M),2,0,Math.PI*2); ctx.fill(); }

        // Matrix points (approx quicklook anchors)
        const matrix=[
            {name:'Sandstone', N:0.60, M:55, c:'#f2cc60'},
            {name:'Limestone', N:0.50, M:80, c:'#7ee787'},
            {name:'Dolomite', N:0.40, M:95, c:'#a371f7'}
        ];
        matrix.forEach(m=>{ ctx.fillStyle=m.c; ctx.beginPath(); ctx.arc(sx(m.N),sy(m.M),5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=m.c; ctx.font='11px DM Sans'; ctx.fillText(m.name,sx(m.N)+7,sy(m.M)-6); });

        // Matrix trend polygon
        ctx.strokeStyle='#f0883e'; ctx.setLineDash([5,4]); ctx.lineWidth=1.2;
        ctx.beginPath(); ctx.moveTo(sx(matrix[0].N),sy(matrix[0].M)); ctx.lineTo(sx(matrix[1].N),sy(matrix[1].M)); ctx.lineTo(sx(matrix[2].N),sy(matrix[2].M)); ctx.stroke(); ctx.setLineDash([]);

        // Axes labels
        ctx.fillStyle='#c9d1d9'; ctx.font='12px DM Sans'; ctx.textAlign='center';
        ctx.fillText('N parameter', margin.left+w/2, canvas.height-14);
        ctx.save(); ctx.translate(18, margin.top+h/2); ctx.rotate(-Math.PI/2); ctx.fillText('M parameter',0,0); ctx.restore();
    }

    // ─── Petrophysics ────────────────────────────────────────
    _renderPetrophysics() {
        if (!this.renderer) return;
        const result = document.getElementById('petroResults');
        if (!result) return;

        // Archie parameters
        const a = parseFloat(document.getElementById('archA')?.value || '1');
        const m = parseFloat(document.getElementById('archM')?.value || '2');
        const n = parseFloat(document.getElementById('archN')?.value || '2');
        const rw = parseFloat(document.getElementById('archRw')?.value || '0.1');

        const rtPack = this._getCurveByFamily('RT');
        const nphiPack = this._getCurveByFamily('NPHI');
        const rhobPack = this._getCurveByFamily('RHOB');
        const grPack = this._getCurveByFamily('GR');
        const rt = rtPack?.data;
        const nphi = nphiPack?.data;
        const rhob = rhobPack?.data;
        const gr = grPack?.data;

        if (!rt || !nphi) {
            result.innerHTML = '<p style="color:#8b949e">Need resistivity + NPHI-family curves for calculation.</p>';
            return;
        }

        // Calculate Sw (multi-model)
        const satModel = document.getElementById('satModel')?.value || 'archie';
        const sw = [];
        const vsh = [];
        const phie = [];
        const grValid = gr ? gr.filter(v => v !== null && !isNaN(v)) : [];
        let grMax = 150, grMin = 0;
        if (grValid.length > 0) {
            grMin = grValid[0]; grMax = grValid[0];
            for (const v of grValid) { if (v < grMin) grMin = v; if (v > grMax) grMax = v; }
        }

        for (let i = 0; i < rt.length; i++) {
            const rtVal = rt[i];
            const nphiVal = nphi[i];
            const rhobVal = rhob?.[i];
            const grVal = gr?.[i];

            // Porosity from NPHI-RHOB crossplot
            let phi = nphiVal;
            if (rhobVal && nphiVal) {
                phi = (nphiVal + (2.65 - rhobVal) / (2.65 - 1.0)) / 2;
            }

            // Vshale from GR
            let vshVal = 0;
            if (grVal !== null && grVal !== undefined) {
                const igr = (grVal - grMin) / (grMax - grMin);
                vshVal = Math.max(0, Math.min(1, igr));
            }

            // Effective porosity
            const phieVal = Math.max(0, phi * (1 - vshVal));

            // Multi-model saturation
            const swVal = this._computeSaturation(satModel, rtVal, phieVal, vshVal, a, m, n, rw);

            sw.push(swVal);
            vsh.push(vshVal);
            phie.push(phieVal);
        }

        // Store computed curves
        this.renderer.curveData['SW'] = sw;
        this.renderer.curveData['VSH'] = vsh;
        this.renderer.curveData['PHIE'] = phie;

        // Update curve config for computed curves
        this.curveConfig['SW'] = { track: 4, color: '#3498db', scale: [0, 1], unit: 'V/V', name: 'Water Saturation' };
        this.curveConfig['VSH'] = { track: 4, color: '#e67e22', scale: [0, 1], unit: 'V/V', name: 'Shale Volume' };
        this.curveConfig['PHIE'] = { track: 4, color: '#2ecc71', scale: [0, 0.4], unit: 'V/V', name: 'Effective Porosity' };

        // Summary stats
        const swValid = sw.filter(v => v !== null && !isNaN(v));
        const vshValid = vsh.filter(v => v !== null && !isNaN(v));
        const phieValid = phie.filter(v => v !== null && !isNaN(v));

        // Quicklook net pay cutoffs (user-editable)
        const vshCut = parseFloat(document.getElementById('cutVsh')?.value || '0.35');
        const phieCut = parseFloat(document.getElementById('cutPhie')?.value || '0.10');
        const swCut = parseFloat(document.getElementById('cutSw')?.value || '0.60');
        let payCount = 0;
        for (let i = 0; i < sw.length; i++) {
            const ok = (vsh[i] ?? 1) < vshCut && (phie[i] ?? 0) > phieCut && (sw[i] ?? 1) < swCut;
            if (ok) payCount += 1;
        }
        const mdStep = Math.abs((this.renderer.depthData?.[1] ?? 0) - (this.renderer.depthData?.[0] ?? 0)) || 0;
        const netPay = payCount * mdStep;
        const gross = (this.renderer.depthData?.length ?? 0) * mdStep;
        const ntg = gross > 0 ? netPay / gross : 0;

        const avg = arr => arr.length ? (arr.reduce((s, v) => s + v, 0) / arr.length).toFixed(4) : 'N/A';

        // Build reservoir intervals from pay flag
        const depth = this.renderer.depthData || [];
        const pay = sw.map((_, i) => ((vsh[i] ?? 1) < vshCut && (phie[i] ?? 0) > phieCut && (sw[i] ?? 1) < swCut) ? 1 : 0);
        const intervals = [];
        let i = 0;
        while (i < pay.length) {
            if (!pay[i]) { i++; continue; }
            const s = i;
            while (i < pay.length && pay[i]) i++;
            const e = i - 1;
            const len = (depth[e] ?? 0) - (depth[s] ?? 0);
            if (len >= (mdStep * 3)) {
                const sl = sw.slice(s, e+1).filter(v=>v!=null && !isNaN(v));
                const pl = phie.slice(s, e+1).filter(v=>v!=null && !isNaN(v));
                const vl = vsh.slice(s, e+1).filter(v=>v!=null && !isNaN(v));
                const mean = a => a.length ? a.reduce((x,y)=>x+y,0)/a.length : 0;
                intervals.push({ top: depth[s], base: depth[e], gross: len, phie: mean(pl), sw: mean(sl), vsh: mean(vl) });
            }
        }

        this._petroCache = { intervals, gross, netPay, ntg, vshCut, phieCut, swCut, mdStep };
        const rows = intervals.map((z,idx)=>`<tr><td>Z${idx+1}</td><td>${z.top.toFixed(1)}</td><td>${z.base.toFixed(1)}</td><td>${z.gross.toFixed(1)}</td><td>${z.phie.toFixed(3)}</td><td>${z.sw.toFixed(3)}</td><td>${z.vsh.toFixed(3)}</td></tr>`).join('') || '<tr><td colspan="7">No pay intervals under current cutoffs</td></tr>';

        result.innerHTML = `
            <div class="petro-summary">
                <h4>Computed Curves</h4>
                <div class="petro-stat"><span>Sw (avg):</span> <strong>${avg(swValid)}</strong></div>
                <div class="petro-stat"><span>Vsh (avg):</span> <strong>${avg(vshValid)}</strong></div>
                <div class="petro-stat"><span>PHIE (avg):</span> <strong>${avg(phieValid)}</strong></div>
                <hr>
                <h4>Net Pay Quicklook</h4>
                <div class="petro-stat"><span>Cutoffs:</span> <strong>Vsh&lt;${vshCut}, PHIE&gt;${phieCut}, Sw&lt;${swCut}</strong></div>
                <div class="petro-stat"><span>Gross interval:</span> <strong>${gross.toFixed(1)} ft</strong></div>
                <div class="petro-stat"><span>Net pay:</span> <strong>${netPay.toFixed(1)} ft</strong></div>
                <div class="petro-stat"><span>N/G:</span> <strong>${(ntg*100).toFixed(1)}%</strong></div>
                <h4 style="margin-top:10px">Reservoir Interval Table</h4>
                <div style="overflow:auto"><table class="petro-table"><thead><tr><th>Zone</th><th>Top</th><th>Base</th><th>Gross</th><th>PHIE</th><th>Sw</th><th>Vsh</th></tr></thead><tbody>${rows}</tbody></table></div>
                <hr>
                <h4>Saturation Model: ${satModel.charAt(0).toUpperCase() + satModel.slice(1)}</h4>
                <div class="petro-stat"><span>a:</span> <strong>${a}</strong></div>
                <div class="petro-stat"><span>m:</span> <strong>${m}</strong></div>
                ${satModel === 'archie' ? '<div class="petro-stat"><span>n:</span> <strong>'+n+'</strong></div>' : ''}
                <div class="petro-stat"><span>Rw:</span> <strong>${rw}</strong></div>
            </div>
        `;

        // Refresh viewer
        this.renderer.render();
    }

    async _renderZoneStats() {
        if (!this.currentWell) return;
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/zone-stats`);
            if (!data?.zones?.length) {
                GeoToast.info('No zones defined. Add zones first.');
                return;
            }
            let html = '<h3 style="color:#c9d1d9;margin:12px 0 8px">Zone Statistics</h3>';
            html += '<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:11px;font-family:IBM Plex Mono,monospace">';
            html += '<thead><tr style="background:#161b22">';
            const headers = ['Zone', 'Top', 'Base', 'Gross', 'Net Pay', 'NTG', 'Avg PHIE', 'Avg Sw', 'Avg Vsh', 'Avg K', 'Points'];
            for (const h of headers) html += `<th style="padding:4px 6px;border:1px solid #30363d;color:#58a6ff;white-space:nowrap">${h}</th>`;
            html += '</tr></thead><tbody>';
            const fmt = (v, digits = 3) => (v !== null && v !== undefined && Number.isFinite(Number(v)) ? Number(v).toFixed(digits) : '-');
            for (const z of data.zones) {
                html += '<tr>';
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${z.name || '-'}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${fmt(z.top_depth, 1)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${fmt(z.bottom_depth, 1)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${fmt(z.gross_ft, 1)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#3fb950">${fmt(z.net_pay_ft, 1)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#d29922">${fmt(z.ntg, 2)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${fmt(z.avg_phie)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${fmt(z.avg_sw)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${fmt(z.avg_vsh)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${fmt(z.avg_k)}</td>`;
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#8b949e">${z.points ?? '-'}</td>`;
                html += '</tr>';
            }
            html += '</tbody></table></div>';
            const el = document.getElementById('petroResults');
            if (el) el.innerHTML = html + el.innerHTML;
        } catch (e) { GeoToast.error(e.message); }
    }

    // ─── QC / Reliability ───────────────────────────────────
    _renderQC() {
        if (!this.renderer) return;
        const panel = document.getElementById('qcContent');
        if (!panel) return;

        const zscore = (arr) => {
            const n = arr.length;
            if (!n) return {mean:0,std:0};
            const mean = arr.reduce((s,v)=>s+v,0)/n;
            const std = Math.sqrt(arr.reduce((s,v)=>s+(v-mean)**2,0)/n) || 1e-9;
            return {mean,std};
        };

        const rows = [];
        for (const [mn, data] of Object.entries(this.renderer.curveData || {})) {
            if (mn === 'DEPT' || !Array.isArray(data)) continue;
            const total = data.length;
            const valid = data.filter(v => v !== null && v !== undefined && !isNaN(v));
            const missing = total - valid.length;
            const missPct = total ? (missing/total)*100 : 0;
            const {mean,std} = zscore(valid);
            let out = 0;
            for (const v of valid) if (Math.abs((v-mean)/std) > 3) out++;
            const outPct = valid.length ? (out/valid.length)*100 : 0;

            let tag = 'HIGH';
            let color = '#3fb950';
            if (missPct > 20 || outPct > 8) { tag = 'LOW'; color = '#f85149'; }
            else if (missPct > 8 || outPct > 4) { tag = 'MEDIUM'; color = '#d29922'; }

            rows.push({mn,total,valid:valid.length,missPct,outPct,mean,std,tag,color});
        }

        rows.sort((a,b)=> (a.tag===b.tag?0:(a.tag==='LOW'?-1:a.tag==='MEDIUM'&&b.tag==='HIGH'?-1:1)));

        const anomalyNotes = [];
        const gapDetails = [];
        const longGapCurves = rows.filter(r => (r.total - r.valid) > 0 && r.missPct > 10).map(r => r.mn);
        if (longGapCurves.length) anomalyNotes.push(`Missing intervals likely on ${longGapCurves.join(', ')}`);

        const depth = this.renderer.depthData || [];
        for (const [mn, data] of Object.entries(this.renderer.curveData || {})) {
            if (!Array.isArray(data) || !data.length || !depth.length) continue;
            let s = -1;
            for (let i = 0; i < data.length; i++) {
                const miss = data[i] == null || isNaN(data[i]);
                if (miss && s < 0) s = i;
                if (!miss && s >= 0) {
                    if (i - s >= 20) {
                        gapDetails.push(`${mn}: ${depth[s]?.toFixed?.(1) ?? s} - ${depth[i - 1]?.toFixed?.(1) ?? (i - 1)} ft`);
                    }
                    s = -1;
                }
            }
            if (s >= 0 && (data.length - s) >= 20) {
                gapDetails.push(`${mn}: ${depth[s]?.toFixed?.(1) ?? s} - ${depth[data.length - 1]?.toFixed?.(1) ?? (data.length - 1)} ft`);
            }
        }

        const calPack = this._getCurveByFamily('CAL');
        if (calPack?.data?.length) {
            const cal = calPack.data.filter(v => v != null && !isNaN(v));
            if (cal.length) {
                const meanCal = cal.reduce((s,v)=>s+v,0)/cal.length;
                if (meanCal > 9.7) anomalyNotes.push(`Washout risk: mean CAL ${meanCal.toFixed(2)} in`);
            }
        }

        const deep = this.renderer.curveData['RILD'] || this.renderer.curveData['ILD'] || this.renderer.curveData['RT'];
        const shallow = this.renderer.curveData['RILM'] || this.renderer.curveData['ILM'] || this.renderer.curveData['MSFL'] || this.renderer.curveData['RXO'];
        if (Array.isArray(deep) && Array.isArray(shallow)) {
            let n = 0, bad = 0;
            for (let i = 0; i < Math.min(deep.length, shallow.length); i++) {
                const d = deep[i], s = shallow[i];
                if (d == null || s == null || isNaN(d) || isNaN(s) || d <= 0 || s <= 0) continue;
                n += 1;
                const ratio = d / s;
                if (ratio < 0.67 || ratio > 1.5) bad += 1;
            }
            if (n > 30 && (bad / n) > 0.35) anomalyNotes.push(`Deep/Shallow mismatch ${(bad / n * 100).toFixed(1)}%`);
        }

        const htmlRows = rows.map(r => `
            <tr>
              <td><strong>${r.mn}</strong></td>
              <td>${r.total}</td>
              <td>${r.valid}</td>
              <td>${r.missPct.toFixed(2)}%</td>
              <td>${r.outPct.toFixed(2)}%</td>
              <td>${r.mean.toFixed(3)}</td>
              <td>${r.std.toFixed(3)}</td>
              <td><span style="color:${r.color};font-weight:700">${r.tag}</span></td>
            </tr>
        `).join('');

        const lowCount = rows.filter(r=>r.tag==='LOW').length;
        const medCount = rows.filter(r=>r.tag==='MEDIUM').length;
        const highCount = rows.filter(r=>r.tag==='HIGH').length;
        const smallSampleCurves = rows.filter(r => r.valid < 30).map(r => r.mn);
        const smallSampleWarn = smallSampleCurves.length
            ? `<div class="petro-stat"><span>Confidence:</span> <strong style="color:#d29922">LOW sample on ${smallSampleCurves.join(', ')} (valid<30)</strong></div>`
            : `<div class="petro-stat"><span>Confidence:</span> <strong style="color:#3fb950">OK sample size</strong></div>`;

        const score = Math.max(0, 100 - (lowCount * 25) - (medCount * 10) - (anomalyNotes.length * 8) - Math.min(gapDetails.length, 10) * 2);
        let grade = 'A';
        let gradeColor = '#3fb950';
        if (score < 75) { grade = 'B'; gradeColor = '#d29922'; }
        if (score < 55) { grade = 'C'; gradeColor = '#f85149'; }

        const recs = [];
        if (lowCount) recs.push('Reprocess low-quality curves (despike + depth-match + merge)');
        if (gapDetails.length) recs.push('Fill/flag long missing intervals before net-pay decision');
        if (anomalyNotes.some(x => x.includes('Washout'))) recs.push('Apply borehole/washout correction before petrophysics');
        if (anomalyNotes.some(x => x.includes('Deep/Shallow'))) recs.push('Review invasion profile; validate Rt source for Archie');
        if (!recs.length) recs.push('QC acceptable for quicklook interpretation');

        panel.innerHTML = `
            <div class="petro-summary" style="margin-bottom:10px">
                <div class="petro-stat"><span>Reliability Summary:</span> <strong>HIGH ${highCount} • MEDIUM ${medCount} • LOW ${lowCount}</strong></div>
                ${smallSampleWarn}
                <div class="petro-stat"><span>Rules:</span> <strong>LOW if missing>20% or outlier>8%</strong></div>
                <div class="petro-stat"><span>Advanced QC:</span> <strong>${anomalyNotes.length ? anomalyNotes.join(' • ') : 'No major anomaly flags'}</strong></div>
                <div class="petro-stat"><span>Gap intervals:</span> <strong>${gapDetails.length ? gapDetails.slice(0,6).join(' • ') : 'No long gaps detected'}</strong></div>
                <div class="petro-stat"><span>QC Grade:</span> <strong style="color:${gradeColor}">${grade} (${score.toFixed(0)}/100)</strong></div>
                <div class="petro-stat"><span>Recommendation:</span> <strong>${recs.join(' • ')}</strong></div>
            </div>
            <div style="overflow:auto">
              <table class="petro-table">
                <thead>
                  <tr><th>Curve</th><th>Total</th><th>Valid</th><th>Missing%</th><th>Outlier%</th><th>Mean</th><th>Std</th><th>Reliability</th></tr>
                </thead>
                <tbody>${htmlRows || '<tr><td colspan="8">No curve data</td></tr>'}</tbody>
              </table>
            </div>
        `;
    }

    // ─── Statistics ──────────────────────────────────────────
    _renderStatistics() {
        if (!this.renderer) return;
        const panel = document.getElementById('statsContent');
        if (!panel) return;

        let html = '<div class="stats-table">';
        html += '<div class="stats-header"><span>Curve</span><span>Unit</span><span>Min</span><span>Max</span><span>Mean</span><span>Median</span><span>Std</span><span>Count</span><span>Null%</span></div>';

        for (const track of this.renderer.tracks) {
            for (const mn of track.curves) {
                const stats = this.renderer.getCurveStats(mn);
                if (!stats) continue;
                const cfg = this.curveConfig[mn] || {};
                html += `<div class="stats-row">
                    <span style="color:${cfg.color || '#58a6ff'};font-weight:600">${mn}</span>
                    <span>${cfg.unit || ''}</span>
                    <span>${stats.min.toFixed(3)}</span>
                    <span>${stats.max.toFixed(3)}</span>
                    <span>${stats.mean.toFixed(3)}</span>
                    <span>${stats.median.toFixed(3)}</span>
                    <span>${stats.std.toFixed(3)}</span>
                    <span>${stats.count}</span>
                    <span>${((stats.null_count / (stats.count + stats.null_count)) * 100).toFixed(1)}%</span>
                </div>`;
            }
        }
        html += '</div>';
        panel.innerHTML = html;
    }

    exportZonationReport() {
        if (!this.currentWell || !this._petroCache) {
            GeoToast.warn('Run petrophysics calculation first');
            return;
        }
        const z = this._petroCache;
        const lines = [];
        lines.push('section,key,value');
        lines.push(`well,name,${this.currentWell.name}`);
        lines.push(`well,uwi,${this.currentWell.uwi || ''}`);
        lines.push(`cutoff,vsh_max,${z.vshCut}`);
        lines.push(`cutoff,phie_min,${z.phieCut}`);
        lines.push(`cutoff,sw_max,${z.swCut}`);
        lines.push(`summary,gross_ft,${z.gross.toFixed(2)}`);
        lines.push(`summary,net_pay_ft,${z.netPay.toFixed(2)}`);
        lines.push(`summary,ntg_pct,${(z.ntg * 100).toFixed(2)}`);
        lines.push('');
        lines.push('zones,zone,top_ft,base_ft,gross_ft,avg_phie,avg_sw,avg_vsh');
        if (!z.intervals.length) {
            lines.push('zones,None,,,,,,');
        } else {
            z.intervals.forEach((it, idx) => {
                lines.push(`zones,Z${idx + 1},${it.top.toFixed(2)},${it.base.toFixed(2)},${it.gross.toFixed(2)},${it.phie.toFixed(4)},${it.sw.toFixed(4)},${it.vsh.toFixed(4)}`);
            });
        }
        const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${this.currentWell.name || 'well'}_zonation_report.csv`;
        a.click();
        GeoToast.success('Zonation report exported');
    }

    async exportBulkPackage() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        try {
            const pkg = await this._api(`/wells/${this.currentWell.id}/export-package`);
            pkg.interpretation = this._petroCache ? {
                cutoffs: { vsh_max: this._petroCache.vshCut, phie_min: this._petroCache.phieCut, sw_max: this._petroCache.swCut },
                gross: this._petroCache.gross,
                net_pay: this._petroCache.netPay,
                ntg: this._petroCache.ntg,
                intervals: this._petroCache.intervals,
            } : null;
            pkg.correlation_markers = this.corrMarkers || [];
            const blob = new Blob([JSON.stringify(pkg, null, 2)], { type: 'application/json' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${this.currentWell.name || 'well'}_export_package.json`;
            a.click();
            GeoToast.success('Export package downloaded');
        } catch (e) {
            GeoToast.error('Export failed: ' + e.message);
        }
    }
    // ─── Saturation Model Selector ───────────────────────────
    _onSatModelChange() {
        const model = document.getElementById('satModel')?.value || 'archie';
        // Show/hide n parameter for non-Archie models
        const nRow = document.getElementById('archN')?.closest('.form-row');
        if (nRow) nRow.style.display = model === 'archie' ? '' : 'none';
    }

    // ─── Petro Template Presets ───────────────────────────────
    applyPetroTemplate(template) {
        const presets = {
            sandstone: { a: 1.0, m: 2.0, n: 2.0, rw: 0.05, vsh: 0.35, phie: 0.10, sw: 0.60, model: 'archie' },
            carbonate: { a: 1.0, m: 2.0, n: 2.0, rw: 0.02, vsh: 0.25, phie: 0.05, sw: 0.50, model: 'archie' },
            shaly_sand: { a: 1.0, m: 1.8, n: 1.8, rw: 0.08, vsh: 0.40, phie: 0.08, sw: 0.70, model: 'simandoux' },
        };
        const p = presets[template];
        if (!p) return;
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        set('archA', p.a); set('archM', p.m); set('archN', p.n); set('archRw', p.rw);
        set('cutVsh', p.vsh); set('cutPhie', p.phie); set('cutSw', p.sw);
        set('satModel', p.model);
        this._onSatModelChange();
        GeoToast.success('Template "' + template + '" applied');
    }

    // ─── Save/Load Petro Params ──────────────────────────────
    async savePetroParams() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const getVal = (id) => parseFloat(document.getElementById(id)?.value || '0');
        const model = document.getElementById('satModel')?.value || 'archie';
        await this._api(`/wells/${this.currentWell.id}/petro-params`, {
            method: 'POST',
            body: JSON.stringify({
                saturation_model: model,
                a: getVal('archA'), m: getVal('archM'), n: getVal('archN'), rw: getVal('archRw'),
                vsh_cutoff: getVal('cutVsh'), phie_cutoff: getVal('cutPhie'), sw_cutoff: getVal('cutSw'),
                template: 'custom',
            }),
        });
        GeoToast.success('Petro params saved');
    }

    async loadPetroParams() {
        if (!this.currentWell) return;
        try {
            const p = await this._api(`/wells/${this.currentWell.id}/petro-params`);
            if (!p) return;
            const set = (id, v) => { const el = document.getElementById(id); if (el && v !== null && v !== undefined) el.value = v; };
            set('archA', p.a); set('archM', p.m); set('archN', p.n); set('archRw', p.rw);
            set('cutVsh', p.vsh_cutoff); set('cutPhie', p.phie_cutoff); set('cutSw', p.sw_cutoff);
            set('satModel', p.saturation_model);
            this._onSatModelChange();
        } catch (e) { /* ignore if not saved yet */ }
    }

    // ─── Unit Normalization ──────────────────────────────────
    _onUnitChange() {
        const mode = document.getElementById('unitToggle')?.value || 'native';
        this._unitMode = mode;
        if (this.renderer) this.renderer.render();
        GeoToast.info('Unit mode: ' + mode);
    }

    _convertValue(val, mnemonic) {
        const mode = this._unitMode || 'native';
        if (mode === 'native' || val === null || val === undefined || isNaN(val)) return val;
        const m = mnemonic.toUpperCase();
        // Depth: FT <-> M
        if (['DEPT', 'DEPTH', 'MD', 'TVD'].includes(m)) {
            return mode === 'metric' ? val * 0.3048 : val / 0.3048;
        }
        // Resistivity: ohm.m <-> ohm.ft
        if (['RT', 'RESD', 'RILD', 'ILD', 'ILM', 'RILM', 'RLL3', 'RLLS', 'MSFL', 'RXO', 'SFLU', 'SFLA'].includes(m)) {
            return mode === 'metric' ? val / 0.3048 : val * 0.3048;
        }
        // Sonic: us/ft <-> us/m
        if (['DT', 'DTC', 'DTP', 'DTS'].includes(m)) {
            return mode === 'metric' ? val / 0.3048 : val * 0.3048;
        }
        // Density: g/cc <-> kg/m3
        if (['RHOB', 'RHOZ'].includes(m)) {
            return mode === 'metric' ? val * 1000 : val / 1000;
        }
        return val;
    }

    _getDepthUnitLabel() {
        const mode = this._unitMode || 'native';
        if (mode === 'metric') return 'm';
        return 'ft';
    }

    // ─── Multi-Mineral Solver (Saturation) ───────────────────
    _computeSaturation(model, rt, phi, vsh, a, m, n, rw) {
        if (rt <= 0 || phi < 0.01) return 1.0;
        let swVal = 1.0;
        if (model === 'simandoux') {
            // Simandoux: Sw^n = (a*Rw)/(phi^m * Rt) - Vsh * Rw / (0.4 * phi)
            const inner = (a * rw) / (Math.pow(phi, m) * rt) - vsh * rw / (0.4 * phi);
            swVal = Math.sqrt(Math.max(0, inner));
        } else if (model === 'indonesian') {
            // Indonesian: 1/Sw^n = sqrt(phi^m/(a*Rw)) + sqrt(Vsh)/sqrt(Rt)
            const denom = Math.sqrt(Math.pow(phi, m) / (a * rw)) + Math.sqrt(Math.max(0, vsh)) / Math.sqrt(Math.max(rt, 0.01));
            swVal = denom > 0 ? 1.0 / (Math.sqrt(Math.max(rt, 0.01)) * denom) : 1.0;
        } else {
            // Archie: Sw^n = a*Rw / (phi^m * Rt)
            swVal = Math.pow(a / (Math.pow(phi, m) * rt / rw), 1 / n);
        }
        return Math.max(0, Math.min(1, swVal));
    }

    // ─── Enhanced Statistics with Histogram ──────────────────
    _renderStatistics() {
        if (!this.renderer) return;
        const panel = document.getElementById('statsContent');
        if (!panel) return;

        let html = '<div class="stats-table">';
        html += '<div class="stats-header"><span>Curve</span><span>Unit</span><span>Min</span><span>Max</span><span>Mean</span><span>Median</span><span>Std</span><span>Count</span><span>Null%</span><span>Skewness</span></div>';

        const histograms = [];
        for (const track of this.renderer.tracks) {
            for (const mn of track.curves) {
                const stats = this.renderer.getCurveStats(mn);
                if (!stats) continue;
                const cfg = this.curveConfig[mn] || {};
                // Compute skewness
                const data = (this.renderer.curveData[mn] || []).filter(v => v !== null && !isNaN(v));
                const mean = stats.mean;
                const std = stats.std || 1e-9;
                let skew = 0;
                if (data.length > 2 && std > 0) {
                    skew = data.reduce((s, v) => s + Math.pow((v - mean) / std, 3), 0) / data.length;
                }
                html += `<div class="stats-row">
                    <span style="color:${cfg.color || '#58a6ff'};font-weight:600">${mn}</span>
                    <span>${cfg.unit || ''}</span>
                    <span>${stats.min.toFixed(3)}</span>
                    <span>${stats.max.toFixed(3)}</span>
                    <span>${stats.mean.toFixed(3)}</span>
                    <span>${stats.median.toFixed(3)}</span>
                    <span>${stats.std.toFixed(3)}</span>
                    <span>${stats.count}</span>
                    <span>${((stats.null_count / (stats.count + stats.null_count)) * 100).toFixed(1)}%</span>
                    <span>${skew.toFixed(2)}</span>
                </div>`;
                if (data.length > 10) histograms.push({ mn, data, color: cfg.color || '#58a6ff', unit: cfg.unit || '' });
            }
        }
        html += '</div>';

        // Histograms
        if (histograms.length > 0) {
            html += '<h3 style="margin:16px 0 8px;color:#c9d1d9">Frequency Distributions</h3>';
            html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:12px">';
            for (const h of histograms.slice(0, 8)) {
                html += `<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px">
                    <div style="color:${h.color};font-weight:600;margin-bottom:6px">${h.mn} <span style="color:#8b949e;font-weight:400;font-size:11px">${h.unit}</span></div>
                    <canvas id="hist_${h.mn}" width="360" height="120"></canvas>
                </div>`;
            }
            html += '</div>';
        }
        panel.innerHTML = html;

        // Draw histograms
        for (const h of histograms.slice(0, 8)) {
            this._drawHistogram(`hist_${h.mn}`, h.data, h.color);
        }
    }

    _drawHistogram(canvasId, data, color) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width, ht = canvas.height;
        const margin = { top: 8, right: 12, bottom: 22, left: 36 };
        const pw = w - margin.left - margin.right;
        const ph = ht - margin.top - margin.bottom;

        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, ht);

        // Build histogram bins
        const sorted = [...data].sort((a, b) => a - b);
        const nBins = 25;
        const min = sorted[Math.floor(sorted.length * 0.01)];
        const max = sorted[Math.floor(sorted.length * 0.99)];
        if (max <= min) return;
        const binW = (max - min) / nBins;
        const bins = new Array(nBins).fill(0);
        for (const v of sorted) {
            if (v < min || v > max) continue;
            const idx = Math.min(nBins - 1, Math.floor((v - min) / binW));
            bins[idx]++;
        }
        const maxBin = Math.max(...bins, 1);

        // Draw bars
        ctx.fillStyle = color + '88';
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        const barW = pw / nBins;
        for (let i = 0; i < nBins; i++) {
            const bh = (bins[i] / maxBin) * ph;
            const x = margin.left + i * barW;
            const y = margin.top + ph - bh;
            ctx.fillRect(x, y, barW - 1, bh);
            ctx.strokeRect(x, y, barW - 1, bh);
        }

        // Axis labels
        ctx.fillStyle = '#8b949e';
        ctx.font = '9px IBM Plex Mono';
        ctx.textAlign = 'center';
        ctx.fillText(min.toFixed(2), margin.left, ht - 4);
        ctx.fillText(max.toFixed(2), w - margin.right, ht - 4);
        ctx.textAlign = 'right';
        ctx.fillText(maxBin.toString(), margin.left - 4, margin.top + 10);
        ctx.fillText('0', margin.left - 4, margin.top + ph);
    }

    // ─── Sensitivity Analysis ────────────────────────────────
    async runSensitivity() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const iterations = parseInt(document.getElementById('sensIter')?.value || '500');
        const pct = parseInt(document.getElementById('sensPct')?.value || '30');
        const model = document.getElementById('satModel')?.value || 'archie';
        const getVal = (id) => parseFloat(document.getElementById(id)?.value || '0');

        GeoLoading.show('Running Monte Carlo (' + iterations + ' iterations)...');
        try {
            const result = await this._api(`/wells/${this.currentWell.id}/sensitivity`, {
                method: 'POST',
                body: JSON.stringify({
                    a: getVal('archA'), m: getVal('archM'), n: getVal('archN'), rw: getVal('archRw'),
                    vsh_cutoff: getVal('cutVsh'), phie_cutoff: getVal('cutPhie'), sw_cutoff: getVal('cutSw'),
                    saturation_model: model, iterations, variation_pct: pct,
                }),
            });

            const panel = document.getElementById('sensResults');
            if (!panel) return;

            panel.innerHTML = `
                <div class="petro-summary">
                    <h4>Monte Carlo Sensitivity Results</h4>
                    <div class="petro-stat"><span>Iterations:</span> <strong>${result.iterations}</strong></div>
                    <div class="petro-stat"><span>Param variation:</span> <strong>±${result.variation_pct}%</strong></div>
                    <div class="petro-stat"><span>Saturation model:</span> <strong>${model}</strong></div>
                    <hr>
                    <h4>Net Pay Uncertainty</h4>
                    <div class="petro-stat"><span>P90 (conservative):</span> <strong style="color:#f85149">${result.p90_net_pay} ft</strong></div>
                    <div class="petro-stat"><span>P50 (most likely):</span> <strong style="color:#d29922">${result.p50_net_pay} ft</strong></div>
                    <div class="petro-stat"><span>P10 (optimistic):</span> <strong style="color:#3fb950">${result.p10_net_pay} ft</strong></div>
                    <div class="petro-stat"><span>Mean ± Std:</span> <strong>${result.mean_net_pay} ± ${result.std_net_pay} ft</strong></div>
                    <hr>
                    <h4>Tornado Chart</h4>
                    <canvas id="tornadoCanvas" width="500" height="250"></canvas>
                    <h4 style="margin-top:12px">Distribution</h4>
                    <canvas id="sensHistogram" width="500" height="160"></canvas>
                </div>
            `;

            // Draw tornado chart (P90-P10 spread visualization)
            this._drawTornado(result);
            this._drawSensHistogram(result);
        } catch (e) {
            GeoToast.error('Sensitivity failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    }

    _drawTornado(result) {
        const canvas = document.getElementById('tornadoCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width, ht = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, ht);

        const margin = { top: 20, right: 30, bottom: 30, left: 100 };
        const pw = w - margin.left - margin.right;
        const ph = ht - margin.top - margin.bottom;

        const center = result.p50_net_pay;
        const half = Math.max(result.p10_net_pay - result.p90_net_pay, 1) / 2;
        const labels = ['P90 (conservative)', 'P50 (base)', 'P10 (optimistic)'];
        const values = [result.p90_net_pay, result.p50_net_pay, result.p10_net_pay];
        const colors = ['#f85149', '#d29922', '#3fb950'];

        const barH = ph / 4;
        const xScale = (v) => margin.left + ((v - (center - half * 1.2)) / (half * 2.4)) * pw;

        for (let i = 0; i < 3; i++) {
            const y = margin.top + (i + 0.5) * barH;
            const x = xScale(values[i]);
            const cx = xScale(center);
            ctx.fillStyle = colors[i] + 'cc';
            ctx.fillRect(Math.min(x, cx), y - barH * 0.35, Math.abs(x - cx), barH * 0.7);

            ctx.fillStyle = '#c9d1d9';
            ctx.font = '12px DM Sans';
            ctx.textAlign = 'right';
            ctx.fillText(labels[i], margin.left - 8, y + 4);

            ctx.fillStyle = '#8b949e';
            ctx.font = '11px IBM Plex Mono';
            ctx.textAlign = 'left';
            ctx.fillText(values[i].toFixed(1) + ' ft', Math.max(x, cx) + 6, y + 4);
        }

        // Center line
        ctx.strokeStyle = '#c9d1d9';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(xScale(center), margin.top);
        ctx.lineTo(xScale(center), margin.top + ph);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = '#8b949e';
        ctx.font = '10px IBM Plex Mono';
        ctx.textAlign = 'center';
        ctx.fillText('Net Pay (ft)', w / 2, ht - 6);
    }

    _drawSensHistogram(result) {
        const canvas = document.getElementById('sensHistogram');
        if (!canvas || !result.histogram_bins || !result.histogram_counts) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width, ht = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, ht);

        const margin = { top: 10, right: 16, bottom: 24, left: 36 };
        const pw = w - margin.left - margin.right;
        const ph = ht - margin.top - margin.bottom;
        const bins = result.histogram_bins;
        const counts = result.histogram_counts;
        const maxCount = Math.max(...counts, 1);
        const barW = pw / counts.length;

        ctx.fillStyle = '#58a6ff88';
        ctx.strokeStyle = '#58a6ff';
        ctx.lineWidth = 1;
        for (let i = 0; i < counts.length; i++) {
            const bh = (counts[i] / maxCount) * ph;
            ctx.fillRect(margin.left + i * barW, margin.top + ph - bh, barW - 1, bh);
            ctx.strokeRect(margin.left + i * barW, margin.top + ph - bh, barW - 1, bh);
        }

        ctx.fillStyle = '#8b949e';
        ctx.font = '9px IBM Plex Mono';
        ctx.textAlign = 'center';
        ctx.fillText(bins[0].toFixed(0), margin.left, ht - 4);
        ctx.fillText(bins[bins.length - 1].toFixed(0), w - margin.right, ht - 4);
        ctx.fillText('Net Pay Distribution (ft)', w / 2, ht - 4);
    }

    // ─── Well Comparison ─────────────────────────────────────
    async loadWellComparison() {
        if (!this.projects || !this.projects.length) return GeoToast.warn('No project loaded');
        const pid = this.projects[0].id;
        GeoLoading.show('Loading comparison...');
        try {
            const data = await this._api(`/projects/${pid}/well-comparison`);
            const panel = document.getElementById('comparisonContent');
            if (!panel) return;

            if (!data.wells || data.wells.length === 0) {
                panel.innerHTML = '<p style="color:#8b949e">No wells in this project.</p>';
                return;
            }

            // Summary table
            let html = '<h3 style="margin:0 0 10px;color:#c9d1d9">Well Summary</h3>';
            html += '<div style="overflow:auto"><table class="petro-table"><thead><tr>';
            html += '<th>Well</th><th>UWI</th><th>Operator</th><th>TD</th><th>Unit</th><th>Runs</th><th>Curves</th><th>Tops</th><th>Zones</th>';
            html += '</tr></thead><tbody>';
            for (const w of data.wells) {
                html += `<tr><td><strong>${w.name}</strong></td><td>${w.uwi || '-'}</td><td>${w.operator || '-'}</td>`;
                html += `<td>${w.total_depth?.toFixed(0) || '-'}</td><td>${w.depth_unit || '-'}</td>`;
                html += `<td>${w.log_run_count}</td><td>${w.curve_count}</td><td>${w.top_count}</td><td>${w.zone_count}</td></tr>`;
            }
            html += '</tbody></table></div>';

            // Curve comparison table
            const allMnemonics = new Set();
            for (const w of data.wells) for (const c of w.curves) allMnemonics.add(c.mnemonic);
            if (allMnemonics.size > 0) {
                html += '<h3 style="margin:16px 0 10px;color:#c9d1d9">Curve Statistics Comparison</h3>';
                html += '<div style="overflow:auto"><table class="petro-table"><thead><tr><th>Curve</th>';
                for (const w of data.wells) html += `<th colspan="3" style="text-align:center;color:#58a6ff">${w.name}</th>`;
                html += '</tr><tr><th></th>';
                for (const _ of data.wells) html += '<th>Mean</th><th>Min</th><th>Max</th>';
                html += '</tr></thead><tbody>';
                for (const mn of [...allMnemonics].sort()) {
                    html += `<tr><td><strong>${mn}</strong></td>`;
                    for (const w of data.wells) {
                        const c = w.curves.find(x => x.mnemonic === mn);
                        if (c && c.count > 0) {
                            html += `<td>${c.mean?.toFixed(3) || '-'}</td><td>${c.min?.toFixed(3) || '-'}</td><td>${c.max?.toFixed(3) || '-'}</td>`;
                        } else {
                            html += '<td>-</td><td>-</td><td>-</td>';
                        }
                    }
                    html += '</tr>';
                }
                html += '</tbody></table></div>';
            }

            panel.innerHTML = html;
        } catch (e) {
            GeoToast.error('Comparison failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    }

    exportComparisonCSV() {
        const table = document.querySelector('#comparisonContent table');
        if (!table) {
            GeoToast.warn('Load comparison first');
            return;
        }
        let csv = '';
        const rows = table.querySelectorAll('tr');
        for (const row of rows) {
            const cells = row.querySelectorAll('th, td');
            csv += Array.from(cells).map(c => {
                const txt = (c.textContent || '').trim().replace(/"/g, '""');
                return `"${txt}"`;
            }).join(',') + '\n';
        }
        const blob = new Blob([csv], { type: 'text/csv' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `well_comparison_${this.projects?.[0]?.name || 'project'}.csv`;
        a.click();
    }




    // ─── Tools Panel Init ────────────────────────────────────
    async _initToolsPanel() {
        if (!this.currentWell) return;
        await this._populateToolRunSelectors();
        await this.loadAnnotations();
        const aliasEl = document.getElementById('aliasStatus');
        if (aliasEl) {
            try {
                const aliases = await this._api(`/wells/${this.currentWell.id}/aliases`);
                aliasEl.textContent = aliases.length ? aliases.length + ' remaps saved' : 'No remaps configured';
            } catch { aliasEl.textContent = 'No remaps'; }
        }
    }

    async _populateToolRunSelectors() {
        if (!this.currentWell) return;
        try {
            const runs = await this._api(`/wells/${this.currentWell.id}/log-runs`);
            const selectors = ['depthShiftRun', 'spliceRunA', 'spliceRunB', 'overlayRunA', 'overlayRunB'];
            for (const id of selectors) {
                const el = document.getElementById(id);
                if (!el) continue;
                el.innerHTML = runs.map(r => '<option value="' + r.id + '">Run ' + r.run_number + ' - ' + r.filename + ' (' + r.num_points + ' pts)</option>').join('');
            }
        } catch { /* no runs */ }
    }

    // ─── Bulk LAS Upload ─────────────────────────────────────
    _initBulkUpload() {
        const input = document.getElementById('bulkFileInput');
        if (!input || input._bound) return;
        input._bound = true;
        input.addEventListener('change', async () => {
            const files = input.files;
            if (!files || !files.length || !this.currentWell) return;
            const status = document.getElementById('bulkUploadStatus');
            if (status) status.textContent = 'Uploading ' + files.length + ' files...';
            GeoLoading.show('Bulk uploading ' + files.length + ' LAS files...');
            let uploaded = 0;
            for (const file of files) {
                try {
                    const formData = new FormData();
                    formData.append('file', file);
                    const resp = await fetch('/api/wells/' + this.currentWell.id + '/upload-las', { method: 'POST', body: formData });
                    if (resp.ok) uploaded++;
                } catch {}
            }
            GeoLoading.hide();
            if (status) status.textContent = uploaded + '/' + files.length + ' uploaded successfully';
            GeoToast.success(uploaded + ' files uploaded');
            await this.selectWell(this.currentWell.id);
            input.value = '';
        });
    }

    // ─── Depth Shift ─────────────────────────────────────────
    async loadDepthShift() {
        const runId = document.getElementById('depthShiftRun')?.value;
        if (!runId) return;
        try {
            const ds = await this._api('/log-runs/' + runId + '/depth-shift');
            const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
            set('depthShiftVal', ds.shift || 0);
            set('depthStretchVal', ds.stretch || 1);
        } catch {}
    }

    async saveDepthShift() {
        const runId = document.getElementById('depthShiftRun')?.value;
        if (!runId) return GeoToast.warn('Select a log run');
        const shift = parseFloat(document.getElementById('depthShiftVal')?.value || '0');
        const stretch = parseFloat(document.getElementById('depthStretchVal')?.value || '1');
        await this._api('/log-runs/' + runId + '/depth-shift', {
            method: 'POST',
            body: JSON.stringify({ shift, stretch }),
        });
        GeoToast.success('Depth shift saved: ' + shift + ' ft, stretch ' + stretch);
    }

    // ─── Curve Splice ────────────────────────────────────────
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
    }

    // ─── Annotations ─────────────────────────────────────────
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
                '<button class="btn-icon-sm" onclick="app.deleteAnnotation(' + a.id + ')" title="Delete"><i data-lucide="x"></i></button>' +
                '</div>'
            ).join('');
            if (typeof lucide !== 'undefined') lucide.createIcons();
        } catch {}
    }

    async addAnnotation() {
        const r = await GeoModal.show({ title: 'Add Annotation', fields: [
            { id: 'depth', label: 'Depth (ft)', type: 'number', step: '0.1', placeholder: '5000.0' },
            { id: 'text', label: 'Note', placeholder: 'Enter annotation text...' },
            { id: 'type', label: 'Type', type: 'select', options: [
                { value: 'note', label: 'Note' }, { value: 'flag', label: 'Flag' }, { value: 'pay', label: 'Pay Zone' }, { value: 'issue', label: 'Issue' },
            ], value: 'note' },
        ]});
        if (!r?.text || isNaN(parseFloat(r.depth))) return;
        await this._api('/wells/' + this.currentWell.id + '/annotations', {
            method: 'POST',
            body: JSON.stringify({ depth: parseFloat(r.depth), text: r.text, annotation_type: r.type || 'note' }),
        });
        GeoToast.success('Annotation added');
        await this.loadAnnotations();
    }

    async deleteAnnotation(aid) {
        await this._api('/annotations/' + aid, { method: 'DELETE' });
        await this.loadAnnotations();
    }

    // ─── Mnemonic Remap ──────────────────────────────────────
    async openMnemonicRemap() {
        if (!this.currentWell || !this.renderer) return GeoToast.warn('Load a well first');
        const currentCurves = Object.keys(this.renderer.curveData || {}).filter(k => k !== 'DEPT');
        const standardMnemonics = ['GR', 'RT', 'RESD', 'ILD', 'NPHI', 'RHOB', 'DT', 'CALI', 'PEF', 'SP'];
        const existing = await this._api('/wells/' + this.currentWell.id + '/aliases').catch(() => []);
        const aliasMap = {};
        existing.forEach(a => { aliasMap[a.original] = a.alias; });

        const fields = currentCurves.map(mn => ({
            id: 'alias_' + mn,
            label: mn + ' → remap to',
            type: 'select',
            options: [{ value: '', label: '(keep as-is)' }, ...standardMnemonics.filter(s => s !== mn).map(s => ({ value: s, label: s }))],
            value: aliasMap[mn] || '',
        }));

        const r = await GeoModal.show({ title: 'Curve Mnemonic Remap', fields });
        if (!r) return;
        const newAliases = [];
        for (const mn of currentCurves) {
            const alias = r['alias_' + mn];
            if (alias && alias !== mn) newAliases.push({ original: mn, alias });
        }
        if (newAliases.length) {
            await this._api('/wells/' + this.currentWell.id + '/aliases', {
                method: 'POST',
                body: JSON.stringify(newAliases),
            });
            GeoToast.success(newAliases.length + ' remaps saved. Reload well to apply.');
        } else {
            GeoToast.info('No remaps configured');
        }
    }

    // ─── Log Run Overlay ─────────────────────────────────────
    async renderOverlay() {
        if (!this.currentWell) return;
        const curve = document.getElementById('overlayCurve')?.value || 'GR';
        const runA = parseInt(document.getElementById('overlayRunA')?.value || '0');
        const runB = parseInt(document.getElementById('overlayRunB')?.value || '0');
        if (!runA || !runB) return GeoToast.warn('Select two runs');

        GeoLoading.show('Loading overlay data...');
        try {
            const [dataA, dataB] = await Promise.all([
                this._loadRunCurveData(runA, curve),
                this._loadRunCurveData(runB, curve),
            ]);
            if (!dataA || !dataB) { GeoToast.warn('Missing curve data'); return; }

            const canvas = document.getElementById('overlayCanvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            canvas.width = canvas.parentElement?.clientWidth || 600;
            canvas.height = 400;
            const w = canvas.width, ht = canvas.height;
            const margin = { top: 30, right: 30, bottom: 40, left: 60 };
            const pw = w - margin.left - margin.right;
            const ph = ht - margin.top - margin.bottom;

            ctx.fillStyle = '#0d1117';
            ctx.fillRect(0, 0, w, ht);

            // Find common depth range
            const allDepths = [...dataA.depth, ...dataB.depth].filter(v => !isNaN(v));
            const dMin = Math.min(...allDepths);
            const dMax = Math.max(...allDepths);
            const allVals = [...dataA.values, ...dataB.values].filter(v => !isNaN(v) && v !== null);
            const vMin = Math.min(...allVals);
            const vMax = Math.max(...allVals);

            const sxD = d => margin.left + ((d - dMin) / (dMax - dMin)) * pw;
            const syV = v => margin.top + ph - ((v - vMin) / (vMax - vMin)) * ph;

            // Grid
            ctx.strokeStyle = '#21262d';
            ctx.lineWidth = 0.5;
            for (let i = 0; i <= 5; i++) {
                const y = margin.top + (ph * i / 5);
                ctx.beginPath(); ctx.moveTo(margin.left, y); ctx.lineTo(margin.left + pw, y); ctx.stroke();
            }

            // Draw Run A
            ctx.strokeStyle = '#58a6ff';
            ctx.lineWidth = 1.5;
            this._drawOverlayCurve(ctx, dataA.depth, dataA.values, sxD, syV, margin, ph);
            // Draw Run B
            ctx.strokeStyle = '#f85149';
            ctx.lineWidth = 1.5;
            this._drawOverlayCurve(ctx, dataB.depth, dataB.values, sxD, syV, margin, ph);

            // Legend
            ctx.fillStyle = '#58a6ff'; ctx.font = '12px DM Sans'; ctx.textAlign = 'left';
            ctx.fillText('Run A', margin.left + 10, margin.top + 16);
            ctx.fillStyle = '#f85149';
            ctx.fillText('Run B', margin.left + 70, margin.top + 16);
            ctx.fillStyle = '#8b949e'; ctx.fillText(curve + ' overlay', margin.left + 130, margin.top + 16);

            // Axes
            ctx.fillStyle = '#c9d1d9'; ctx.font = '11px DM Sans'; ctx.textAlign = 'center';
            ctx.fillText('Depth (ft)', w / 2, ht - 6);
            ctx.save(); ctx.translate(14, margin.top + ph / 2); ctx.rotate(-Math.PI / 2); ctx.fillText(curve, 0, 0); ctx.restore();

        } catch (e) {
            GeoToast.error('Overlay failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    }

    _drawOverlayCurve(ctx, depth, values, sx, sy, margin, ph) {
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < depth.length; i++) {
            if (isNaN(values[i]) || values[i] === null) continue;
            const x = sx(depth[i]);
            const y = sy(values[i]);
            if (y < margin.top || y > margin.top + ph) continue;
            if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }

    async _loadRunCurveData(runId, mnemonic) {
        try {
            const curves = await this._api('/log-runs/' + runId + '/curves');
            const deptCurve = curves.find(c => ['DEPT', 'DEPTH'].includes(c.mnemonic));
            const targetCurve = curves.find(c => c.mnemonic === mnemonic);
            if (!deptCurve || !targetCurve) return null;
            const data = await this._api('/log-runs/' + runId + '/data', {
                method: 'POST',
                body: JSON.stringify({ start: deptCurve.min_value, stop: deptCurve.max_value, curves: [deptCurve.mnemonic, mnemonic] }),
            });
            return { depth: data[deptCurve.mnemonic] || [], values: data[mnemonic] || [] };
        } catch { return null; }
    }

    // ─── Print Report ────────────────────────────────────────
    async generatePrintReport() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        GeoLoading.show('Generating report...');
        try {
            const data = await this._api('/wells/' + this.currentWell.id + '/report');
            let html = '<!DOCTYPE html><html><head><meta charset="UTF-8">';
            html += '<title>GeoLog Report - ' + (data.well?.name || 'Unknown') + '</title>';
            html += '<style>';
            html += 'body{font-family:Arial,sans-serif;margin:40px;color:#1a1a1a;font-size:11px}';
            html += 'h1{font-size:20px;border-bottom:3px solid #1a1a1a;padding-bottom:8px}';
            html += 'h2{font-size:15px;color:#333;margin-top:24px;border-bottom:1px solid #ccc;padding-bottom:4px}';
            html += 'table{border-collapse:collapse;width:100%;margin:8px 0}';
            html += 'th,td{border:1px solid #ccc;padding:5px 8px;text-align:left;font-size:10px}';
            html += 'th{background:#f0f0f0;font-weight:700}';
            html += '.header-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:12px 0}';
            html += '.header-item{padding:6px 10px;background:#f8f8f8;border-left:3px solid #333}';
            html += '.header-item label{font-weight:700;display:block;font-size:9px;text-transform:uppercase;color:#666}';
            html += '.header-item span{font-size:13px;color:#1a1a1a}';
            html += '@media print{body{margin:20px}}';
            html += '</style></head><body>';
            html += '<h1>Well Log Interpretation Report</h1>';

            // Well info
            html += '<div class="header-grid">';
            const w = data.well || {};
            const info = [
                ['Well Name', w.name], ['UWI', w.uwi], ['Operator', w.operator],
                ['Field', w.field_name], ['Total Depth', w.total_depth + ' ' + (w.depth_unit || 'FT')],
                ['Spud Date', w.spud_date || 'N/A'],
            ];
            for (const [label, val] of info) {
                html += '<div class="header-item"><label>' + label + '</label><span>' + (val || 'N/A') + '</span></div>';
            }
            html += '</div>';

            // Formation Tops
            if (data.formation_tops?.length) {
                html += '<h2>Formation Tops</h2><table><thead><tr><th>Formation</th><th>Depth</th><th>Lithology</th><th>Color</th></tr></thead><tbody>';
                for (const t of data.formation_tops) {
                    html += '<tr><td>' + t.formation_name + '</td><td>' + (t.depth?.toFixed(1) || '-') + '</td><td>' + (t.lithology || '-') + '</td><td style="background:' + (t.color || '#fff') + '">' + (t.color || '-') + '</td></tr>';
                }
                html += '</tbody></table>';
            }

            // Zones
            if (data.zones?.length) {
                html += '<h2>Interpretation Zones</h2><table><thead><tr><th>Zone</th><th>Top</th><th>Base</th><th>Gross</th></tr></thead><tbody>';
                for (const z of data.zones) {
                    html += '<tr><td>' + z.name + '</td><td>' + z.top_depth + '</td><td>' + z.bottom_depth + '</td><td>' + (z.bottom_depth - z.top_depth).toFixed(1) + '</td></tr>';
                }
                html += '</tbody></table>';
            }

            // Petrophysics params
            if (data.petro_params) {
                const pp = data.petro_params;
                html += '<h2>Petrophysics Parameters</h2><div class="header-grid">';
                const pItems = [
                    ['Model', pp.saturation_model], ['a', pp.a], ['m', pp.m], ['n', pp.n], ['Rw', pp.rw],
                    ['Vsh cutoff', pp.vsh_cutoff], ['PHIE cutoff', pp.phie_cutoff], ['Sw cutoff', pp.sw_cutoff],
                ];
                for (const [label, val] of pItems) {
                    html += '<div class="header-item"><label>' + label + '</label><span>' + val + '</span></div>';
                }
                html += '</div>';
            }

            // Curve summary
            if (data.curve_summary?.length) {
                html += '<h2>Curve Data Summary</h2><table><thead><tr><th>Run</th><th>Curve</th><th>Unit</th><th>Count</th><th>Min</th><th>Max</th><th>Mean</th></tr></thead><tbody>';
                for (const c of data.curve_summary) {
                    html += '<tr><td>' + c.run + '</td><td>' + c.mnemonic + '</td><td>' + (c.unit || '') + '</td><td>' + c.count + '</td><td>' + (c.min?.toFixed(4) || '-') + '</td><td>' + (c.max?.toFixed(4) || '-') + '</td><td>' + (c.mean?.toFixed(4) || '-') + '</td></tr>';
                }
                html += '</tbody></table>';
            }

            html += '<p style="margin-top:30px;color:#999;font-size:9px">Generated by GeoLog Professional — ' + (data.generated_at || new Date().toISOString()) + '</p>';
            html += '</body></html>';

            const blob = new Blob([html], { type: 'text/html' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = (this.currentWell.name || 'well') + '_report.html';
            a.click();
            GeoToast.success('Report downloaded — open in browser to print');
        } catch (e) {
            GeoToast.error('Report failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    }


    // --- Electrofacies Panel ---
    _initFaciesPanel() {
        if (!this.renderer) return;
        const container = document.getElementById('faciesCurveCheckboxes');
        if (!container || container.children.length > 0) return;
        const curves = Object.keys(this.renderer.curveData || {}).filter(k => k !== 'DEPT');
        container.innerHTML = curves.map(mn =>
            '<label style="display:flex;align-items:center;gap:4px;font-size:12px;color:#c9d1d9;background:#161b22;padding:4px 8px;border-radius:4px;border:1px solid #30363d">' +
            '<input type="checkbox" value="' + mn + '" ' + (['GR','RHOB','NPHI','RT'].includes(mn) ? 'checked' : '') + '> ' + mn + '</label>'
        ).join('');
    }

    async runElectrofacies() {
        if (!this.currentWell || !this.currentLogRun) return GeoToast.warn('Load a well first');
        const n = parseInt(document.getElementById('faciesN')?.value || '4');
        const checks = document.querySelectorAll('#faciesCurveCheckboxes input:checked');
        const curves = Array.from(checks).map(c => c.value);
        if (curves.length < 2) return GeoToast.warn('Select at least 2 curves');
        GeoLoading.show('Running K-means clustering...');
        try {
            const result = await this._api('/wells/' + this.currentWell.id + '/electrofacies', {
                method: 'POST',
                body: JSON.stringify({ log_run_id: this.currentLogRun.id, n_clusters: n, curves }),
            });
            this._faciesData = result;
            this.renderer.curveData['FACIES'] = result.facies_labels;
            this.curveConfig['FACIES'] = { track: 5, color: '#a371f7', scale: [0, result.n_clusters], unit: '', name: 'Electrofacies' };
            const panel = document.getElementById('faciesResults');
            if (!panel) return;
            const colors = ['#58a6ff', '#3fb950', '#f0883e', '#f85149', '#a371f7', '#f2cc60', '#79c0ff', '#d2a8ff'];
            let html = '<div class="petro-summary"><h4>Electrofacies Classification</h4>';
            html += '<div class="petro-stat"><span>Algorithm:</span> <strong>K-means (' + result.n_clusters + ')</strong></div>';
            html += '<div class="petro-stat"><span>Curves:</span> <strong>' + result.curves_used.join(', ') + '</strong></div>';
            html += '<div class="petro-stat"><span>Points:</span> <strong>' + result.facies_labels.filter(l => l >= 0).length + '</strong></div>';
            html += '<hr><h4>Facies Summary</h4>';
            html += '<div style="overflow:auto"><table class="petro-table"><thead><tr><th>Color</th><th>Facies</th><th>Count</th><th>Pct</th>';
            for (const k of result.curves_used) html += '<th>' + k + '</th>';
            html += '</tr></thead><tbody>';
            for (let i = 0; i < result.summary.length; i++) {
                const s = result.summary[i];
                html += '<tr><td style="background:' + colors[i % colors.length] + '"></td>';
                html += '<td><strong>' + s.facies + '</strong></td><td>' + s.count + '</td><td>' + s.pct + '%</td>';
                for (const k of result.curves_used) html += '<td>' + (s.centroid[k]?.toFixed(3) || '-') + '</td>';
                html += '</tr>';
            }
            html += '</tbody></table></div></div>';
            panel.innerHTML = html;
            this.renderer.render();
            GeoToast.success('Electrofacies: ' + result.n_clusters + ' types');
        } catch (e) { GeoToast.error('Clustering failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    }

    toggleLithTrack() {
        if (!this.renderer) return;
        this._showLithTrack = !this._showLithTrack;
        this.renderer._showLithology = this._showLithTrack;
        this.renderer.render();
        GeoToast.info('Lith track: ' + (this._showLithTrack ? 'ON' : 'OFF'));
    }

    async runCurveFilter(type) {
        if (!this.currentLogRun) return GeoToast.warn('Select a log run');
        const curves = Object.keys(this.renderer?.curveData || {}).filter(k => !['DEPT','SW','VSH','PHIE','FACIES'].includes(k));
        const r = await GeoModal.show({ title: type + ' filter', fields: [
            { id: 'mnemonic', label: 'Curve', type: 'select', options: curves.map(c => ({ value: c, label: c })), value: curves[0] || 'GR' },
            { id: 'window', label: 'Window (odd)', type: 'number', value: type === 'despike' ? '5' : '7', step: '2' },
        ]});
        if (!r?.mnemonic) return;
        GeoLoading.show('Filtering...');
        try {
            const result = await this._api('/log-runs/' + this.currentLogRun.id + '/filter', {
                method: 'POST', body: JSON.stringify({ mnemonic: r.mnemonic, filter: type, window: parseInt(r.window) }),
            });
            GeoToast.success('Created: ' + result.new_curve);
            await this._loadCurveData();
        } catch (e) { GeoToast.error('Filter failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    }

    async runAutoDepthMatch() {
        if (!this.currentWell) return GeoToast.warn('No well');
        await this._populateToolRunSelectors();
        const sel = document.getElementById('depthShiftRun');
        const runs = Array.from(sel?.options || []).map(o => ({ value: o.value, label: o.text }));
        const r = await GeoModal.show({ title: 'Auto Depth Match', fields: [
            { id: 'run_a', label: 'Reference Run', type: 'select', options: runs },
            { id: 'run_b', label: 'Match Run', type: 'select', options: runs },
            { id: 'mnemonic', label: 'Curve', type: 'select', options: [{value:'GR',label:'GR'},{value:'RT',label:'RT'},{value:'NPHI',label:'NPHI'},{value:'RHOB',label:'RHOB'}] },
            { id: 'max_shift', label: 'Max shift (ft)', type: 'number', value: '50' },
        ]});
        if (!r?.run_a || !r?.run_b) return;
        GeoLoading.show('Cross-correlating...');
        try {
            const result = await this._api('/wells/' + this.currentWell.id + '/depth-match', {
                method: 'POST', body: JSON.stringify({ run_a: parseInt(r.run_a), run_b: parseInt(r.run_b), mnemonic: r.mnemonic, max_shift: parseFloat(r.max_shift) }),
            });
            GeoToast.success('Shift: ' + result.optimal_shift_ft + ' ft (r=' + result.correlation + ')', 5000);
            const si = document.getElementById('depthShiftVal'); if (si) si.value = result.optimal_shift_ft;
            const rs = document.getElementById('depthShiftRun'); if (rs) rs.value = r.run_b;
        } catch (e) { GeoToast.error('Match failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    }

    async runCurveOverride() {
        if (!this.currentLogRun) return GeoToast.warn('Select a log run');
        const curves = Object.keys(this.renderer?.curveData || {}).filter(k => k !== 'DEPT');
        const r = await GeoModal.show({ title: 'Curve Override', fields: [
            { id: 'mnemonic', label: 'Curve', type: 'select', options: curves.map(c => ({ value: c, label: c })) },
            { id: 'start', label: 'Start depth', type: 'number', step: '0.1' },
            { id: 'end', label: 'End depth', type: 'number', step: '0.1' },
            { id: 'value', label: 'Override value', type: 'number', step: '0.01' },
        ]});
        if (!r?.mnemonic || isNaN(parseFloat(r.start)) || isNaN(parseFloat(r.end))) return;
        try {
            await this._api('/log-runs/' + this.currentLogRun.id + '/curve-override', {
                method: 'POST', body: JSON.stringify({ mnemonic: r.mnemonic, start: parseFloat(r.start), end: parseFloat(r.end), value: parseFloat(r.value) }),
            });
            GeoToast.success('Override applied');
            await this._loadCurveData();
        } catch (e) { GeoToast.error('Override failed: ' + e.message); }
    }
    // --- Multi-well Strip Log ---
    async renderStripLog() {
        if (!this.projects?.length) return;
        const curve = document.getElementById('stripCurve')?.value || 'GR';
        const refFormation = document.getElementById('stripRefFormation')?.value || '';
        const pid = this.projects[0].id;
        GeoLoading.show('Loading strip log data...');
        try {
            const data = await this._api('/projects/' + pid + '/strip-log-data?curve=' + curve);
            if (!data.wells?.length) { GeoToast.warn('No wells with data'); return; }

            // Populate formation selector
            const sel = document.getElementById('stripRefFormation');
            if (sel && sel.options.length <= 1) {
                for (const fn of (data.formation_names || [])) {
                    sel.add(new Option(fn, fn));
                }
            }

            const canvas = document.getElementById('stripLogCanvas');
            if (!canvas) return;
            const wells = data.wells;
            const nWells = wells.length;
            const stripW = 160;
            const nameW = 100;
            const margin = { top: 50, right: 20, bottom: 30, left: 10 };
            canvas.width = margin.left + nameW + nWells * stripW + margin.right;
            canvas.height = 800;
            const ctx = canvas.getContext('2d');
            const w = canvas.width, ht = canvas.height;
            ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, w, ht);

            // Find global depth range
            let dMin = Infinity, dMax = -Infinity;
            let vMin = Infinity, vMax = -Infinity;
            for (const well of wells) {
                if (refFormation) {
                    const top = well.tops.find(t => t.name === refFormation);
                    if (top) {
                        const normalized = well.depth.map(d => d - top.depth);
                        dMin = Math.min(dMin, ...normalized); dMax = Math.max(dMax, ...normalized);
                    } else {
                        dMin = Math.min(dMin, ...well.depth); dMax = Math.max(dMax, ...well.depth);
                    }
                } else {
                    dMin = Math.min(dMin, ...well.depth); dMax = Math.max(dMax, ...well.depth);
                }
                const validVals = well.values.filter(v => v !== null && !isNaN(v));
                if (validVals.length) { vMin = Math.min(vMin, ...validVals); vMax = Math.max(vMax, ...validVals); }
            }
            if (!isFinite(dMin)) return;
            const plotTop = margin.top, plotBottom = ht - margin.bottom;
            const plotH = plotBottom - plotTop;
            const sy = d => plotTop + ((d - dMin) / (dMax - dMin)) * plotH;
            const sx = (v, stripX) => stripX + 10 + ((v - vMin) / (vMax - vMin)) * (stripW - 20);

            // Draw wells
            const colors = ['#58a6ff', '#3fb950', '#f0883e', '#f85149', '#a371f7', '#f2cc60', '#79c0ff', '#d2a8ff'];
            for (let wi = 0; wi < nWells; wi++) {
                const well = wells[wi];
                const stripX = margin.left + nameW + wi * stripW;

                // Strip background
                ctx.fillStyle = '#161b22'; ctx.fillRect(stripX, plotTop, stripW, plotH);
                ctx.strokeStyle = '#30363d'; ctx.lineWidth = 1; ctx.strokeRect(stripX, plotTop, stripW, plotH);

                // Well name header
                ctx.fillStyle = colors[wi % colors.length]; ctx.font = 'bold 12px DM Sans'; ctx.textAlign = 'center';
                ctx.fillText(well.name, stripX + stripW / 2, plotTop - 20);
                ctx.fillStyle = '#8b949e'; ctx.font = '10px DM Sans';
                ctx.fillText(well.uwi || '', stripX + stripW / 2, plotTop - 8);

                // Draw curve
                ctx.strokeStyle = colors[wi % colors.length]; ctx.lineWidth = 1.2; ctx.beginPath();
                let started = false;
                for (let i = 0; i < well.depth.length; i++) {
                    const d = refFormation ? (well.depth[i] - (well.tops.find(t => t.name === refFormation)?.depth || 0)) : well.depth[i];
                    const v = well.values[i];
                    if (v === null || isNaN(v)) continue;
                    const y = sy(d); const x = sx(v, stripX);
                    if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
                }
                ctx.stroke();

                // Draw formation tops as horizontal lines
                for (const top of well.tops) {
                    const d = refFormation ? (top.depth - (well.tops.find(t => t.name === refFormation)?.depth || 0)) : top.depth;
                    const y = sy(d);
                    if (y < plotTop || y > plotBottom) continue;
                    ctx.strokeStyle = top.color || '#888'; ctx.lineWidth = 1.5;
                    ctx.beginPath(); ctx.moveTo(stripX, y); ctx.lineTo(stripX + stripW, y); ctx.stroke();
                    ctx.fillStyle = top.color || '#888'; ctx.font = '9px DM Sans'; ctx.textAlign = 'left';
                    ctx.fillText(top.name, stripX + 4, y - 3);
                }
            }

            // Draw correlation lines between wells (matching formation tops)
            const allNames = data.formation_names || [];
            for (const fname of allNames) {
                const points = [];
                for (let wi = 0; wi < nWells; wi++) {
                    const well = wells[wi];
                    const top = well.tops.find(t => t.name === fname);
                    if (!top) continue;
                    const d = refFormation ? (top.depth - (well.tops.find(t => t.name === refFormation)?.depth || 0)) : top.depth;
                    const x = margin.left + nameW + wi * stripW + stripW / 2;
                    const y = sy(d);
                    if (y >= plotTop && y <= plotBottom) points.push({ x, y });
                }
                if (points.length >= 2) {
                    ctx.strokeStyle = '#ffffff22'; ctx.lineWidth = 0.8; ctx.setLineDash([4, 4]);
                    ctx.beginPath(); ctx.moveTo(points[0].x, points[0].y);
                    for (let p = 1; p < points.length; p++) ctx.lineTo(points[p].x, points[p].y);
                    ctx.stroke(); ctx.setLineDash([]);
                }
            }

            // Depth axis label
            ctx.fillStyle = '#8b949e'; ctx.font = '10px DM Sans'; ctx.textAlign = 'center';
            const axisLabel = refFormation ? 'Strat Depth from ' + refFormation + ' (ft)' : 'Measured Depth (ft)';
            ctx.fillText(axisLabel, w / 2, ht - 4);

            // Depth ticks
            ctx.font = '9px IBM Plex Mono'; ctx.textAlign = 'right'; ctx.fillStyle = '#8b949e';
            const tickInterval = Math.ceil((dMax - dMin) / 15 / 10) * 10;
            for (let d = Math.ceil(dMin / tickInterval) * tickInterval; d <= dMax; d += tickInterval) {
                const y = sy(d);
                ctx.fillText(d.toFixed(0), margin.left + nameW - 6, y + 3);
                ctx.strokeStyle = '#21262d'; ctx.lineWidth = 0.5;
                ctx.beginPath(); ctx.moveTo(margin.left + nameW, y); ctx.lineTo(w - margin.right, y); ctx.stroke();
            }

            GeoToast.success('Strip log: ' + nWells + ' wells, curve ' + curve);
        } catch (e) { GeoToast.error('Strip log failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    }

    // --- Auto-Pick Formation Tops ---
    async runAutoPickTops() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const curve = document.getElementById('autoPickCurve')?.value || 'GR';
        const threshold = parseFloat(document.getElementById('autoPickThreshold')?.value || '2.0');
        const minGap = parseFloat(document.getElementById('autoPickGap')?.value || '50');
        GeoLoading.show('Auto-picking from ' + curve + '...');
        try {
            const result = await this._api('/wells/' + this.currentWell.id + '/auto-pick-tops', {
                method: 'POST', body: JSON.stringify({ curve, threshold, min_gap: minGap }),
            });
            const panel = document.getElementById('autoPickResults');
            if (!panel) return;
            if (!result.picks?.length) { panel.innerHTML = '<p>No picks found. Try lower sensitivity.</p>'; return; }

            panel.innerHTML = '<p><strong>' + result.picks.length + ' picks found:</strong></p>' +
                result.picks.map(p =>
                    '<div style="display:flex;align-items:center;gap:6px;padding:2px 0">' +
                    '<span style="background:' + p.color + ';width:10px;height:10px;border-radius:50%"></span>' +
                    '<span>' + p.formation_name + ' @ ' + p.depth + ' ft (z=' + p.z_score + ')</span>' +
                    '</div>'
                ).join('') +
                '<button class="btn-sm" onclick="app._saveAutoPicks()" style="margin-top:8px">Save All Picks</button>';

            this._autoPicks = result.picks;
            GeoToast.success(result.picks.length + ' formation tops detected');
        } catch (e) { GeoToast.error('Auto-pick failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    }

    async _saveAutoPicks() {
        if (!this._autoPicks?.length || !this.currentWell) return;
        await this._api('/wells/' + this.currentWell.id + '/save-picks', {
            method: 'POST', body: JSON.stringify({ picks: this._autoPicks }),
        });
        GeoToast.success(this._autoPicks.length + ' tops saved');
        await this._loadFormationTops();
        this._autoPicks = null;
    }

    // --- CSV Upload ---
    _initCSVUpload() {
        const input = document.getElementById('csvFileInput');
        if (!input || input._bound) return;
        input._bound = true;
        input.addEventListener('change', async () => {
            const file = input.files?.[0];
            if (!file || !this.currentWell) return;
            const status = document.getElementById('csvUploadStatus');
            if (status) status.textContent = 'Uploading ' + file.name + '...';
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch('/api/wells/' + this.currentWell.id + '/upload-csv', { method: 'POST', body: formData });
                const result = await resp.json();
                if (resp.ok) {
                    if (status) status.textContent = 'OK: ' + result.curves.length + ' curves, ' + result.points + ' points';
                    GeoToast.success('CSV imported: ' + result.curves.join(', '));
                    await this.selectWell(this.currentWell.id);
                } else {
                    if (status) status.textContent = 'Error: ' + (result.detail || 'Unknown');
                }
            } catch (e) { if (status) status.textContent = 'Error: ' + e.message; }
            input.value = '';
        });
    }

    // --- Well Trajectory ---
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
    }

    async viewTrajectory() {
        if (!this.currentWell) return;
        try {
            const data = await this._api('/wells/' + this.currentWell.id + '/trajectory');
            if (!data.points?.length) { GeoToast.info('No trajectory data'); return; }
            const panel = document.getElementById('trajectoryStatus');
            if (panel) panel.textContent = data.points.length + ' pts, TVD range: ' + data.points[0].tvd + '-' + data.points[data.points.length - 1].tvd + ' ft';
            GeoToast.info('Trajectory loaded: ' + data.points.length + ' points');
        } catch { GeoToast.info('No trajectory data'); }
    }

    // ─── Sprint 21: Probability Plot ──────────────────────────────
    async runProbabilityPlot() {
        if (!this.currentWell) return;
        const curve = document.getElementById('probCurve').value;
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/probability-plot`, {
                method: 'POST', body: JSON.stringify({ curve, n_bins: 20 })
            });
            this._drawProbabilityPlot(data);
            document.getElementById('probResults').innerHTML = `
                <div class="stat-grid">
                    <div class="stat-item"><span class="stat-label">N</span><span class="stat-value">${data.n}</span></div>
                    <div class="stat-item"><span class="stat-label">Mean</span><span class="stat-value">${data.mean.toFixed(3)}</span></div>
                    <div class="stat-item"><span class="stat-label">Std Dev</span><span class="stat-value">${data.std.toFixed(3)}</span></div>
                    <div class="stat-item"><span class="stat-label">P10</span><span class="stat-value">${data.p10.toFixed(3)}</span></div>
                    <div class="stat-item"><span class="stat-label">P50 (Median)</span><span class="stat-value">${data.p50.toFixed(3)}</span></div>
                    <div class="stat-item"><span class="stat-label">P90</span><span class="stat-value">${data.p90.toFixed(3)}</span></div>
                    <div class="stat-item"><span class="stat-label">Skewness</span><span class="stat-value">${data.skewness.toFixed(3)}</span></div>
                </div>`;
        } catch (e) { GeoToast.error(e.message); }
    }

    _drawProbabilityPlot(data) {
        const canvas = document.getElementById('probabilityCanvas');
        const ctx = canvas.getContext('2d');
        const W = canvas.parentElement.clientWidth || 800;
        const H = canvas.parentElement.clientHeight || 500;
        canvas.width = W; canvas.height = H;
        const m = {top: 40, bottom: 50, left: 70, right: 40};
        ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, H);
        const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;

        if (!data.sorted_values.length) {
            ctx.fillStyle = '#8b949e'; ctx.fillText('No data', W/2 - 20, H/2); return;
        }

        const n = data.sorted_values.length;
        const minV = Math.min(...data.sorted_values), maxV = Math.max(...data.sorted_values);
        const range = maxV - minV || 1;

        // Y-axis: probability scale (0.01% to 99.99%)
        function probY(p) {
            // Inverse normal approximation for log-normal probability paper
            const clamped = Math.max(0.0001, Math.min(0.9999, p));
            // Simple linear for now; true prob paper uses inverse normal
            return m.top + plotH * (1 - (Math.log(clamped/(1-clamped)) / 14 + 0.5));
        }

        // Draw grid lines for probability levels
        const gridProbs = [0.01, 0.1, 1, 5, 10, 25, 50, 75, 90, 95, 99, 99.9, 99.99];
        ctx.strokeStyle = '#21262d'; ctx.lineWidth = 0.5;
        ctx.fillStyle = '#8b949e'; ctx.font = '10px IBM Plex Mono';
        ctx.textAlign = 'right';
        for (const pct of gridProbs) {
            const p = pct / 100;
            const y = probY(p);
            if (y < m.top || y > m.top + plotH) continue;
            ctx.beginPath(); ctx.moveTo(m.left, y); ctx.lineTo(m.left + plotW, y); ctx.stroke();
            ctx.fillText(pct + '%', m.left - 5, y + 3);
        }

        // X-axis
        ctx.textAlign = 'center';
        const xStep = Math.pow(10, Math.floor(Math.log10(range / 5)));
        for (let v = Math.floor(minV / xStep) * xStep; v <= maxV + xStep; v += xStep) {
            const x = m.left + ((v - minV) / range) * plotW;
            ctx.fillText(v.toFixed(1), x, H - m.bottom + 15);
            ctx.strokeStyle = '#21262d'; ctx.beginPath(); ctx.moveTo(x, m.top); ctx.lineTo(x, m.top + plotH); ctx.stroke();
        }

        // Plot data points
        ctx.strokeStyle = '#58a6ff'; ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
            const p = (i + 0.5) / n;
            const x = m.left + ((data.sorted_values[i] - minV) / range) * plotW;
            const y = probY(p);
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Mark P10/P50/P90
        const marks = [{v: data.p10, l: 'P10', c: '#f0883e'}, {v: data.p50, l: 'P50', c: '#3fb950'}, {v: data.p90, l: 'P90', c: '#f85149'}];
        for (const mk of marks) {
            const x = m.left + ((mk.v - minV) / range) * plotW;
            ctx.strokeStyle = mk.c; ctx.setLineDash([4,4]); ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(x, m.top); ctx.lineTo(x, m.top + plotH); ctx.stroke();
            ctx.setLineDash([]); ctx.fillStyle = mk.c; ctx.font = 'bold 11px IBM Plex Mono';
            ctx.fillText(mk.l + ': ' + mk.v.toFixed(2), x, m.top - 5);
        }

        // Axis labels
        ctx.fillStyle = '#c9d1d9'; ctx.font = '12px DM Sans'; ctx.textAlign = 'center';
        ctx.fillText(curve + ' Value', m.left + plotW/2, H - 5);
        ctx.save(); ctx.translate(15, m.top + plotH/2); ctx.rotate(-Math.PI/2);
        ctx.fillText('Cumulative Probability', 0, 0); ctx.restore();
    }

    // ─── Sprint 21: Moveable Oil ──────────────────────────────────
    async runMoveableOil() {
        if (!this.currentWell) return;
        const rtCurve = document.getElementById('moiRt').value;
        const rxoCurve = document.getElementById('moiRxo').value;
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/moveable-oil`, {
                method: 'POST', body: JSON.stringify({ rt_curve: rtCurve, rxo_curve: rxoCurve, phie_curve: 'PHIE' })
            });
            this._drawMoveableOilPlot(data);
            const moiAvg = data.moi.filter(v => v != null).reduce((a,b) => a+b, 0) / (data.moi.filter(v=>v!=null).length||1);
            document.getElementById('moiResults').innerHTML = `
                <div class="stat-grid">
                    <div class="stat-item"><span class="stat-label">Points</span><span class="stat-value">${data.depths.length}</span></div>
                    <div class="stat-item"><span class="stat-label">MOI Mean</span><span class="stat-value">${data.stats.mean?.toFixed(4) ?? 'N/A'}</span></div>
                    <div class="stat-item"><span class="stat-label">MOI Median</span><span class="stat-value">${data.stats.median?.toFixed(4) ?? 'N/A'}</span></div>
                    <div class="stat-item"><span class="stat-label">Avg MOI</span><span class="stat-value">${moiAvg.toFixed(2)}</span></div>
                </div>`;
        } catch (e) { GeoToast.error(e.message); }
    }

    _drawMoveableOilPlot(data) {
        const canvas = document.getElementById('moveableCanvas');
        const ctx = canvas.getContext('2d');
        const W = canvas.parentElement.clientWidth || 800;
        const H = canvas.parentElement.clientHeight || 500;
        canvas.width = W; canvas.height = H;
        const m = {top: 40, bottom: 50, left: 70, right: 40};
        ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, H);
        const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;

        if (!data.depths.length) {
            ctx.fillStyle = '#8b949e'; ctx.fillText('No data — need RT and RXO curves', W/2 - 60, H/2); return;
        }

        const depMin = Math.min(...data.depths), depMax = Math.max(...data.depths);
        const depRange = depMax - depMin || 1;

        // Get value range for Rwa/Rxo_wa (log scale)
        const allVals = [...data.rwa, ...data.rxo_wa].filter(v => v != null && v > 0);
        if (!allVals.length) return;
        const logMin = Math.log10(Math.min(...allVals)), logMax = Math.log10(Math.max(...allVals));
        const logRange = logMax - logMin || 1;

        function valToX(v) { return m.left + ((Math.log10(v) - logMin) / logRange) * plotW; }
        function depToY(d) { return m.top + ((d - depMin) / depRange) * plotH; }

        // Draw Rwa curve (blue)
        ctx.strokeStyle = '#58a6ff'; ctx.lineWidth = 1;
        ctx.beginPath(); let started = false;
        for (let i = 0; i < data.depths.length; i++) {
            if (data.rwa[i] == null || data.rwa[i] <= 0) continue;
            const x = valToX(data.rwa[i]), y = depToY(data.depths[i]);
            if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Draw Rxo_wa curve (orange)
        ctx.strokeStyle = '#f0883e'; ctx.lineWidth = 1;
        ctx.beginPath(); started = false;
        for (let i = 0; i < data.depths.length; i++) {
            if (data.rxo_wa[i] == null || data.rxo_wa[i] <= 0) continue;
            const x = valToX(data.rxo_wa[i]), y = depToY(data.depths[i]);
            if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Legend
        ctx.fillStyle = '#58a6ff'; ctx.fillRect(m.left + 10, m.top + 10, 12, 3);
        ctx.fillStyle = '#c9d1d9'; ctx.font = '11px DM Sans'; ctx.textAlign = 'left';
        ctx.fillText('Rwa (apparent Rw)', m.left + 28, m.top + 14);
        ctx.fillStyle = '#f0883e'; ctx.fillRect(m.left + 10, m.top + 28, 12, 3);
        ctx.fillStyle = '#c9d1d9'; ctx.fillText('Rxo_wa (apparent Rxo)', m.left + 28, m.top + 32);

        // Depth axis
        ctx.fillStyle = '#8b949e'; ctx.textAlign = 'right'; ctx.font = '10px IBM Plex Mono';
        const dStep = Math.pow(10, Math.floor(Math.log10(depRange / 8)));
        for (let d = Math.ceil(depMin / dStep) * dStep; d <= depMax; d += dStep) {
            ctx.fillText(d.toFixed(0), m.left - 5, depToY(d) + 3);
        }

        // Title
        ctx.fillStyle = '#c9d1d9'; ctx.textAlign = 'center'; ctx.font = '12px DM Sans';
        ctx.fillText('Rwa vs Rxo_wa (Moveable Oil Indicator)', m.left + plotW/2, H - 5);
    }

    // ─── Sprint 21: Dip Plot ──────────────────────────────────────
    async runDipPlot() {
        if (!this.currentWell) return;
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/dip-plot`, {
                method: 'POST', body: JSON.stringify({})
            });
            this._drawDipPlot(data);
            document.getElementById('dipResults').innerHTML = `
                <div class="stat-grid">
                    <div class="stat-item"><span class="stat-label">Survey Points</span><span class="stat-value">${data.md.length}</span></div>
                    <div class="stat-item"><span class="stat-label">Max Inclination</span><span class="stat-value">${Math.max(...data.inc).toFixed(1)}°</span></div>
                    <div class="stat-item"><span class="stat-label">Max Azimuth</span><span class="stat-value">${Math.max(...data.azi).toFixed(1)}°</span></div>
                </div>`;
        } catch (e) { GeoToast.error(e.message); }
    }

    _drawDipPlot(data) {
        const canvas = document.getElementById('dipCanvas');
        const ctx = canvas.getContext('2d');
        const W = canvas.parentElement.clientWidth || 800;
        const H = canvas.parentElement.clientHeight || 500;
        canvas.width = W; canvas.height = H;
        const m = {top: 40, bottom: 50, left: 70, right: 40};
        ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, H);
        const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;

        if (!data.md.length) {
            ctx.fillStyle = '#8b949e'; ctx.fillText('No deviation survey data', W/2 - 60, H/2); return;
        }

        const depMin = Math.min(...data.md), depMax = Math.max(...data.md);
        const depRange = depMax - depMin || 1;
        const maxInc = Math.max(...data.inc, 10);

        function depToY(d) { return m.top + ((d - depMin) / depRange) * plotH; }

        // Draw tadpoles
        for (let i = 0; i < data.md.length; i++) {
            const y = depToY(data.md[i]);
            const inc = data.inc[i];
            const azi = data.azi[i];
            const radius = (inc / maxInc) * (plotW / 2 - 20);
            const centerX = m.left + plotW / 2;
            const radAzi = (azi - 90) * Math.PI / 180; // rotate so North is up
            const dotX = centerX + radius * Math.cos(radAzi);
            const dotY = y + radius * Math.sin(radAzi);

            // Tail (from center to dot, dashed)
            ctx.strokeStyle = '#58a6ff44'; ctx.lineWidth = 0.5; ctx.setLineDash([2,2]);
            ctx.beginPath(); ctx.moveTo(centerX, y); ctx.lineTo(dotX, dotY); ctx.stroke();
            ctx.setLineDash([]);

            // Dot
            ctx.fillStyle = inc > 10 ? '#f0883e' : (inc > 5 ? '#d29922' : '#3fb950');
            ctx.beginPath(); ctx.arc(dotX, dotY, 3, 0, Math.PI * 2); ctx.fill();

            // Depth label
            ctx.fillStyle = '#8b949e'; ctx.font = '9px IBM Plex Mono'; ctx.textAlign = 'right';
            ctx.fillText(data.md[i].toFixed(0), m.left - 5, y + 3);
        }

        // Center vertical line
        ctx.strokeStyle = '#30363d'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(m.left + plotW/2, m.top); ctx.lineTo(m.left + plotW/2, m.top + plotH); ctx.stroke();

        // Compass labels
        ctx.fillStyle = '#c9d1d9'; ctx.font = '11px DM Sans'; ctx.textAlign = 'center';
        ctx.fillText('N', m.left + plotW/2, m.top - 10);
        ctx.fillText('S', m.left + plotW/2, m.top + plotH + 15);
        ctx.fillText('E', m.left + plotW - 10, m.top + plotH/2);
        ctx.fillText('W', m.left + 15, m.top + plotH/2);

        // Title
        ctx.fillText('Tadpole / Dip Plot', m.left + plotW/2, H - 5);
    }

    // ─── Sprint 22: Buckles Plot ─────────────────────────────────
    async runBuckles() {
        if (!this.currentWell) return;
        const phie = document.getElementById('buckPhie')?.value || 'NPHI';
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/buckles`, {
                method: 'POST', body: JSON.stringify({ phie_curve: phie })
            });
            this._drawBucklesPlot(data);
            document.getElementById('buckResults').innerHTML = `
                <div class="stat-grid">
                    <div class="stat-item"><span class="stat-label">Points</span><span class="stat-value">${data.depths.length}</span></div>
                    <div class="stat-item"><span class="stat-label">Mean BVW</span><span class="stat-value">${data.stats.mean_bvw.toFixed(4)}</span></div>
                    <div class="stat-item"><span class="stat-label">Pay Fraction</span><span class="stat-value">${(data.stats.pay_fraction * 100).toFixed(1)}%</span></div>
                </div>`;
        } catch (e) { GeoToast.error(e.message); }
    }

    _drawBucklesPlot(data) {
        const canvas = document.getElementById('bucklesCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.parentElement.clientWidth || 800;
        const H = canvas.parentElement.clientHeight || 500;
        canvas.width = W; canvas.height = H;
        const m = {top: 40, bottom: 50, left: 70, right: 40};
        ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, H);
        const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;
        if (!data.depths.length) { ctx.fillStyle = '#8b949e'; ctx.fillText('No data', W/2 - 20, H/2); return; }
        const depMin = Math.min(...data.depths), depMax = Math.max(...data.depths);
        const depRange = depMax - depMin || 1;
        const maxBvw = Math.max(...data.bvw.filter(v => v != null), 0.2);
        function depToY(d) { return m.top + ((d - depMin) / depRange) * plotH; }
        function bvwToX(b) { return m.left + (b / maxBvw) * plotW; }
        // Cutoff lines
        for (const [val, label, color] of [[0.04, 'Tight', '#f85149'], [0.12, 'Pay', '#3fb950']]) {
            const x = bvwToX(val);
            ctx.strokeStyle = color; ctx.setLineDash([6,4]); ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.moveTo(x, m.top); ctx.lineTo(x, m.top + plotH); ctx.stroke();
            ctx.setLineDash([]); ctx.fillStyle = color; ctx.font = 'bold 11px IBM Plex Mono';
            ctx.textAlign = 'center'; ctx.fillText(label + ' (' + val + ')', x, m.top - 5);
        }
        // Plot dots
        for (let i = 0; i < data.depths.length; i++) {
            if (data.bvw[i] == null) continue;
            const x = bvwToX(data.bvw[i]), y = depToY(data.depths[i]);
            ctx.fillStyle = data.bvw[i] > 0.12 ? '#f85149' : (data.bvw[i] > 0.04 ? '#d29922' : '#3fb950');
            ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2); ctx.fill();
        }
        // Axes
        ctx.fillStyle = '#8b949e'; ctx.font = '10px IBM Plex Mono'; ctx.textAlign = 'center';
        for (let v = 0; v <= maxBvw; v += 0.04) {
            ctx.fillText(v.toFixed(2), bvwToX(v), m.top + plotH + 15);
        }
        ctx.textAlign = 'right';
        const dStep = Math.pow(10, Math.floor(Math.log10(depRange / 8)));
        for (let d = Math.ceil(depMin / dStep) * dStep; d <= depMax; d += dStep) {
            ctx.fillText(d.toFixed(0), m.left - 5, depToY(d) + 3);
        }
        ctx.fillStyle = '#c9d1d9'; ctx.font = '12px DM Sans'; ctx.textAlign = 'center';
        ctx.fillText('Bulk Volume Water (BVW)', m.left + plotW/2, H - 5);
    }

    // ─── Sprint 22: Hingle Plot ──────────────────────────────────
    async runHingle() {
        if (!this.currentWell) return;
        const rt = document.getElementById('hingleRt')?.value || 'RT';
        const phie = document.getElementById('hinglePhie')?.value || 'NPHI';
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/hingle`, {
                method: 'POST', body: JSON.stringify({ rt_curve: rt, phie_curve: phie })
            });
            this._drawHinglePlot(data);
            document.getElementById('hingleResults').innerHTML = `
                <div class="stat-grid">
                    <div class="stat-item"><span class="stat-label">Points</span><span class="stat-value">${data.x.length}</span></div>
                    <div class="stat-item"><span class="stat-label">Rw Estimate</span><span class="stat-value">${data.rw_line?.slope ? (1/data.rw_line.slope).toFixed(4) : 'N/A'}</span></div>
                </div>`;
        } catch (e) { GeoToast.error(e.message); }
    }

    _drawHinglePlot(data) {
        const canvas = document.getElementById('hingleCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.parentElement.clientWidth || 800;
        const H = canvas.parentElement.clientHeight || 500;
        canvas.width = W; canvas.height = H;
        const m = {top: 40, bottom: 50, left: 70, right: 40};
        ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, H);
        const plotW = W - m.left - m.right, plotH = H - m.top - m.bottom;
        if (!data.x.length) { ctx.fillStyle = '#8b949e'; ctx.fillText('No data', W/2 - 20, H/2); return; }
        const xMin = Math.min(...data.x), xMax = Math.max(...data.x);
        const yMin = Math.min(...data.y), yMax = Math.max(...data.y);
        const xRange = xMax - xMin || 1, yRange = yMax - yMin || 1;
        function xToPixel(v) { return m.left + ((v - xMin) / xRange) * plotW; }
        function yToPixel(v) { return m.top + plotH - ((v - yMin) / yRange) * plotH; }
        // Grid
        ctx.strokeStyle = '#21262d'; ctx.lineWidth = 0.5;
        for (let v = Math.ceil(xMin * 20) / 20; v <= xMax; v += Math.max(0.01, xRange / 10)) {
            const x = xToPixel(v);
            ctx.beginPath(); ctx.moveTo(x, m.top); ctx.lineTo(x, m.top + plotH); ctx.stroke();
        }
        // Plot points
        for (let i = 0; i < data.x.length; i++) {
            const px = xToPixel(data.x[i]), py = yToPixel(data.y[i]);
            ctx.fillStyle = '#58a6ff88';
            ctx.beginPath(); ctx.arc(px, py, 2.5, 0, Math.PI * 2); ctx.fill();
        }
        // Rw line
        if (data.rw_line && data.rw_line.slope) {
            ctx.strokeStyle = '#f85149'; ctx.lineWidth = 1.5; ctx.setLineDash([4,4]);
            ctx.beginPath();
            ctx.moveTo(xToPixel(xMin), yToPixel(data.rw_line.slope * xMin + data.rw_line.intercept));
            ctx.lineTo(xToPixel(xMax), yToPixel(data.rw_line.slope * xMax + data.rw_line.intercept));
            ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle = '#f85149'; ctx.font = 'bold 11px DM Sans'; ctx.textAlign = 'left';
            ctx.fillText('Rw line', xToPixel(xMax) - 60, yToPixel(data.rw_line.slope * xMax + data.rw_line.intercept) - 8);
        }
        // Axes
        ctx.fillStyle = '#8b949e'; ctx.font = '10px IBM Plex Mono'; ctx.textAlign = 'center';
        const xTickStep = Math.max(0.05, Math.round(xRange * 10) / 100);
        for (let v = Math.ceil(xMin / xTickStep) * xTickStep; v <= xMax + xTickStep; v += xTickStep) {
            ctx.fillText(v.toFixed(2), xToPixel(v), m.top + plotH + 15);
        }
        ctx.textAlign = 'right';
        const yTickStep = Math.pow(10, Math.floor(Math.log10(yRange / 6)));
        for (let v = Math.ceil(yMin / yTickStep) * yTickStep; v <= yMax + yTickStep; v += yTickStep) {
            ctx.fillText(v.toFixed(3), m.left - 5, yToPixel(v) + 3);
        }
        ctx.fillStyle = '#c9d1d9'; ctx.font = '12px DM Sans'; ctx.textAlign = 'center';
        ctx.fillText('Porosity (v/v)', m.left + plotW/2, H - 5);
        ctx.save(); ctx.translate(15, m.top + plotH/2); ctx.rotate(-Math.PI/2);
        ctx.fillText('1/Rt (1/ohm.m)', 0, 0); ctx.restore();
    }

    // ─── Sprint 22: Curve Calculator ─────────────────────────────
    async runCurveCalc() {
        if (!this.currentWell) return;
        const expr = document.getElementById('calcExpr')?.value;
        const name = (document.getElementById('calcName')?.value || 'NEW_CURVE').toUpperCase();
        if (!expr) { GeoToast.warning('Enter an expression'); return; }
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/curve-calc`, {
                method: 'POST', body: JSON.stringify({ expression: expr, output_name: name })
            });
            document.getElementById('calcResults').innerHTML = `
                <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin-top:8px">
                    <strong style="color:#3fb950">✓ Curve created</strong><br>
                    <span style="color:#c9d1d9">${data.curve_name}</span> — ${data.points} points<br>
                    Min: ${data.min.toFixed(3)} | Max: ${data.max.toFixed(3)} | Mean: ${data.mean.toFixed(3)}
                </div>`;
            GeoToast.success(`Curve ${data.curve_name} created (${data.points} points)`);
            await this.selectLogRun(this.currentLogRun.id);
        } catch (e) { GeoToast.error(e.message); }
    }

    // ─── Sprint 23: Data Table ────────────────────────────────────
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
            for (const c of cols) html += `<th style="border:1px solid #30363d;padding:4px 8px;color:#58a6ff;cursor:pointer" onclick="app._sortDataTable('${c}')">${c}</th>`;
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
    }

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
        for (const c of cols) html += `<th style="border:1px solid #30363d;padding:4px 8px;color:#58a6ff;cursor:pointer" onclick="app._sortDataTable('${c}')">${c}</th>`;
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
    }

    exportDataTableCSV() {
        if (!this._lastDataTable) { GeoToast.warning('Load data first'); return; }
        const data = this._lastDataTable;
        let csv = data.columns.join(',') + '\n';
        for (const row of data.rows) csv += row.map(v => v === null ? '' : v).join(',') + '\n';
        const blob = new Blob([csv], { type: 'text/csv' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = `${this.currentWell?.name || 'data'}_table.csv`; a.click();
    }

    // ─── Sprint 23: Tops Management ──────────────────────────────
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
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${t.formation_name}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${t.depth.toFixed(1)}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${t.top_depth?.toFixed(1) ?? '-'}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${t.base_depth?.toFixed(1) ?? '-'}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d"><span style="display:inline-block;width:16px;height:16px;border-radius:3px;background:${t.color}"></span></td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${t.lithology || '-'}</td>`;
            html += `<td style="padding:4px 6px;border:1px solid #21262d">`;
            html += `<button class="btn-sm" onclick="app.editFormationTop(${t.id})" style="font-size:10px">✏️</button> `;
            html += `<button class="btn-sm" onclick="app.deleteFormationTop(${t.id})" style="font-size:10px;color:#f85149">🗑️</button>`;
            html += '</td></tr>';
        }
        html += '</tbody></table></div>';
        if (!tops.length) html = '<p style="color:#8b949e">No formation tops. Add one from the viewer toolbar or import CSV.</p>';
        document.getElementById('topsMgmtContent').innerHTML = html;
    }

    async exportTopsCSV() {
        if (!this.projects?.[0]) return;
        const pid = this.projects[0].id;
        try {
            const resp = await fetch(`/api/projects/${pid}/tops-export`);
            const text = await resp.text();
            const blob = new Blob([text], { type: 'text/csv' });
            const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
            a.download = `tops_project_${pid}.csv`; a.click();
            GeoToast.success('Tops exported');
        } catch (e) { GeoToast.error(e.message); }
    }

    async exportTopsPetrel() {
        if (!this.currentWell) return;
        try {
            const resp = await fetch(`/api/wells/${this.currentWell.id}/tops-petrel`);
            const text = await resp.text();
            const blob = new Blob([text], { type: 'text/csv' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `tops_petrel_${this.currentWell.name}.csv`;
            a.click();
            GeoToast.success('Petrel-format tops exported');
        } catch (e) { GeoToast.error(e.message); }
    }

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
    }

    async deleteFormationTop(id) {
        if (!confirm('Delete this formation top?')) return;
        try {
            await this._api(`/tops/${id}`, { method: 'DELETE' });
            this.formationTops = await this._api(`/wells/${this.currentWell.id}/tops`);
            this._renderTopsManagement();
            if (this.renderer) this.renderer.formationTops = this.formationTops;
            GeoToast.success('Top deleted');
        } catch (e) { GeoToast.error(e.message); }
    }

    // ─── Sprint 24: Well Location Map ─────────────────────────────
    async renderWellMap() {
        if (!this.projects?.[0]) return;
        const canvas = document.getElementById('mapCanvas');
        const results = document.getElementById('mapResults');
        if (!canvas || !results) return;

        const container = canvas.parentElement;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const rect = container?.getBoundingClientRect();
        const width = Math.max(320, Math.floor(rect?.width || 800));
        const height = Math.max(280, Math.floor(rect?.height || 420));
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        const drawPlaceholder = (msg) => {
            ctx.fillStyle = '#0d1117';
            ctx.fillRect(0, 0, width, height);
            ctx.strokeStyle = '#30363d';
            ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
            ctx.fillStyle = '#8b949e';
            ctx.font = '14px DM Sans';
            ctx.textAlign = 'center';
            ctx.fillText(msg, width / 2, height / 2);
        };

        try {
            const pid = this.projects[0].id;
            const rows = await this._api(`/projects/${pid}/well-locations`);
            const wells = (rows || []).filter(w => Number.isFinite(Number(w.latitude)) && Number.isFinite(Number(w.longitude)));

            if (!wells.length) {
                drawPlaceholder('No well coordinates available. Edit wells to add lat/lon.');
                results.innerHTML = '<p style="color:#8b949e">No well coordinates available. Edit wells to add lat/lon.</p>';
                canvas.onclick = null;
                return;
            }

            const lats = wells.map(w => Number(w.latitude));
            const lons = wells.map(w => Number(w.longitude));
            const minLat = Math.min(...lats);
            const maxLat = Math.max(...lats);
            const minLon = Math.min(...lons);
            const maxLon = Math.max(...lons);
            const latRange = Math.max(1e-9, maxLat - minLat);
            const lonRange = Math.max(1e-9, maxLon - minLon);
            const pad = 32;
            const plotW = width - pad * 2;
            const plotH = height - pad * 2;

            const points = wells.map(w => {
                const lon = Number(w.longitude);
                const lat = Number(w.latitude);
                const x = pad + ((lon - minLon) / lonRange) * plotW;
                const y = height - pad - ((lat - minLat) / latRange) * plotH;
                return { ...w, x, y };
            });

            ctx.fillStyle = '#0d1117';
            ctx.fillRect(0, 0, width, height);
            ctx.strokeStyle = '#30363d';
            ctx.strokeRect(0.5, 0.5, width - 1, height - 1);

            ctx.strokeStyle = '#21262d';
            ctx.lineWidth = 1;
            for (let i = 0; i < 4; i++) {
                const gx = pad + (plotW * i / 3);
                const gy = pad + (plotH * i / 3);
                ctx.beginPath(); ctx.moveTo(gx, pad); ctx.lineTo(gx, height - pad); ctx.stroke();
                ctx.beginPath(); ctx.moveTo(pad, gy); ctx.lineTo(width - pad, gy); ctx.stroke();
            }

            for (const p of points) {
                const isCurrent = this.currentWell?.id === p.id;
                ctx.beginPath();
                ctx.arc(p.x, p.y, isCurrent ? 5 : 3.5, 0, Math.PI * 2);
                ctx.fillStyle = isCurrent ? '#3fb950' : '#ffffff';
                ctx.fill();

                ctx.font = '11px DM Sans';
                ctx.textAlign = 'left';
                ctx.fillStyle = isCurrent ? '#3fb950' : '#c9d1d9';
                ctx.fillText(p.name || `Well ${p.id}`, p.x + 7, p.y - 6);
            }

            results.innerHTML = `
                <div style="display:flex;gap:12px;flex-wrap:wrap;color:#8b949e;font-size:12px">
                    <span><strong style="color:#c9d1d9">Wells:</strong> ${points.length}</span>
                    <span><strong style="color:#c9d1d9">Latitude:</strong> ${minLat.toFixed(5)} to ${maxLat.toFixed(5)}</span>
                    <span><strong style="color:#c9d1d9">Longitude:</strong> ${minLon.toFixed(5)} to ${maxLon.toFixed(5)}</span>
                </div>`;

            canvas.onclick = async (e) => {
                const r = canvas.getBoundingClientRect();
                const mx = e.clientX - r.left;
                const my = e.clientY - r.top;
                let nearest = null;
                let best = 12;
                for (const p of points) {
                    const d = Math.hypot(mx - p.x, my - p.y);
                    if (d < best) {
                        nearest = p;
                        best = d;
                    }
                }
                if (nearest?.id && nearest.id !== this.currentWell?.id) {
                    await this.selectWell(nearest.id);
                    this.renderWellMap();
                }
            };
        } catch (e) {
            GeoToast.error(e.message);
            drawPlaceholder('Failed to load well locations.');
            results.innerHTML = '<p style="color:#f0883e">Failed to load well locations.</p>';
            canvas.onclick = null;
        }
    }

    // ─── Sprint 24: Project Summary Dashboard ─────────────────────
    async loadDashboard() {
        if (!this.projects?.[0]) return;
        try {
            const data = await this._api(`/projects/${this.projects[0].id}/summary`);
            let html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-bottom:20px">';
            const cards = [
                ['Wells', data.total_wells, '#58a6ff'],
                ['Log Runs', data.total_log_runs, '#3fb950'],
                ['Formation Tops', data.total_tops, '#f0883e'],
                ['Zones', data.total_zones, '#d29922'],
                ['Unique Formations', (data.unique_formations || []).length, '#bc8cff']
            ];
            for (const [label, value, color] of cards) {
                html += `<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px;text-align:center">
                    <div style="font-size:28px;font-weight:700;color:${color}">${value ?? 0}</div>
                    <div style="font-size:12px;color:#8b949e;margin-top:4px">${label}</div>
                </div>`;
            }
            html += '</div>';
            if (data.wells?.length) {
                html += '<h3 style="color:#c9d1d9;margin:12px 0 8px">Well Details</h3>';
                html += '<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px">';
                html += '<thead><tr style="background:#161b22">';
                for (const h of ['Well', 'UWI', 'Runs', 'Tops', 'Zones', 'Gross (ft)', 'TD (ft)']) {
                    html += `<th style="padding:6px;border:1px solid #30363d;color:#58a6ff;text-align:left">${h}</th>`;
                }
                html += '</tr></thead><tbody>';
                for (const w of data.wells) {
                    html += '<tr>';
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${w.name || '-'}</td>`;
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#8b949e">${w.uwi || '-'}</td>`;
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9;text-align:center">${w.log_runs ?? 0}</td>`;
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9;text-align:center">${w.tops ?? 0}</td>`;
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9;text-align:center">${w.zones ?? 0}</td>`;
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9;text-align:right">${Number(w.gross_ft || 0).toFixed(1)}</td>`;
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9;text-align:right">${w.total_depth !== null && w.total_depth !== undefined ? Number(w.total_depth).toFixed(1) : '-'}</td>`;
                    html += '</tr>';
                }
                html += '</tbody></table></div>';
            }
            if (data.unique_formations?.length) {
                html += '<h3 style="color:#c9d1d9;margin:16px 0 8px">Formations</h3>';
                html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
                for (const f of data.unique_formations) {
                    html += `<span style="background:#21262d;border:1px solid #30363d;border-radius:6px;padding:4px 10px;font-size:12px;color:#c9d1d9">${f}</span>`;
                }
                html += '</div>';
            }
            document.getElementById('dashboardContent').innerHTML = html;
        } catch (e) { GeoToast.error(e.message); }
    }

    // ─── Sprint 23: Formation Matrix ─────────────────────────────
    async loadFormationMatrix() {
        if (!this.projects?.[0]) return;
        const pid = this.projects[0].id;
        try {
            const data = await this._api(`/projects/${pid}/formation-matrix`);
            let html = '<div style="overflow:auto"><table style="border-collapse:collapse;font-size:12px">';
            html += '<thead><tr style="background:#161b22">';
            html += '<th style="padding:6px 12px;border:1px solid #30363d;color:#58a6ff;text-align:left">Formation</th>';
            for (const w of data.wells) {
                html += `<th style="padding:6px 12px;border:1px solid #30363d;color:#58a6ff;text-align:center">${w.name}</th>`;
            }
            html += '</tr></thead><tbody>';
            for (const form of data.formations) {
                html += '<tr>';
                html += `<td style="padding:4px 12px;border:1px solid #21262d;color:#c9d1d9;font-weight:500">${form}</td>`;
                for (const w of data.wells) {
                    const depth = w.tops[form];
                    if (depth !== undefined && depth !== null) {
                        html += `<td style="padding:4px 12px;border:1px solid #21262d;color:#3fb950;text-align:center">${depth.toFixed(1)}</td>`;
                    } else {
                        html += '<td style="padding:4px 12px;border:1px solid #21262d;color:#484f58;text-align:center">-</td>';
                    }
                }
                html += '</tr>';
            }
            html += '</tbody></table></div>';
            if (!data.formations.length) html = '<p style="color:#8b949e">No formation tops found in this project.</p>';
            document.getElementById('formationMatrixContent').innerHTML = html;
        } catch (e) { GeoToast.error(e.message); }
    }

    // ─── Sprint 23: Batch Petrophysics ────────────────────────────
    async runBatchPetro() {
        if (!this.projects?.[0]) return;
        const pid = this.projects[0].id;
        const params = {
            saturation_model: document.getElementById('batchSatModel').value,
            a: parseFloat(document.getElementById('batchA').value),
            m: parseFloat(document.getElementById('batchM').value),
            n: parseFloat(document.getElementById('batchN').value),
            rw: parseFloat(document.getElementById('batchRw').value),
            vsh_cutoff: parseFloat(document.getElementById('batchVshCut').value),
            phie_cutoff: parseFloat(document.getElementById('batchPhieCut').value),
            sw_cutoff: parseFloat(document.getElementById('batchSwCut').value),
            template: document.getElementById('batchTemplate').value
        };
        try {
            const result = await this._api(`/projects/${pid}/batch-petro`, {
                method: 'POST', body: JSON.stringify(params)
            });
            document.getElementById('batchResults').innerHTML = `
                <div style="background:#161b22;border:1px solid #3fb95033;border-radius:8px;padding:12px;margin-top:8px">
                    <strong style="color:#3fb950">✓ Applied to ${result.updated} wells</strong><br>
                    <span style="color:#c9d1d9">${result.wells.join(', ')}</span>
                </div>`;
            GeoToast.success(`Parameters applied to ${result.updated} wells`);
        } catch (e) { GeoToast.error(e.message); }
    }

    openShortcutHelp() {
        const modal = document.getElementById('shortcutModal');
        if (modal) modal.style.display = 'flex';
    }

    closeShortcutHelp(event = null) {
        if (event && event.target && event.target.id !== 'shortcutModal') return;
        const modal = document.getElementById('shortcutModal');
        if (modal) modal.style.display = 'none';
    }

    _showFirstRunWelcome() {
        if (localStorage.getItem('geolog_welcome_seen')) return;
        setTimeout(() => {
            GeoToast.info('Welcome to GeoLog! Upload a LAS file to begin. Press ? for keyboard shortcuts.', 7000);
            localStorage.setItem('geolog_welcome_seen', '1');
        }, 1200);
    }

    // ─── Sprint 26: Status Bar ──────────────────────────────────
    _updateStatusBar(view) {
        const el = document.getElementById('statusView');
        if (el) {
            const names = { viewer: 'Log Viewer', crossplot: 'Cross Plot', pickett: 'Pickett', mnplot: 'M-N Plot',
                petrophysics: 'Petrophysics', qc: 'QC', statistics: 'Statistics', sensitivity: 'Sensitivity',
                comparison: 'Comparison', correlation: 'Correlation', striplog: 'Strip Log', facies: 'Facies',
                formation: 'Formation', topsmgmt: 'Tops', probability: 'Probability', moveable: 'Moveable Oil',
                dipplot: 'Dip Plot', buckles: 'Buckles', hingle: 'Hingle', tools: 'Tools', calculator: 'Calc',
                datatable: 'Data Table', batch: 'Batch', map: 'Map', dashboard: 'Dashboard', matrix: 'Matrix',
                audit: 'Audit Trail' };
            el.textContent = names[view] || view;
        }
        if (this.currentWell) {
            const w = this.wells.find(w => w.id === this.currentWell);
            const el2 = document.getElementById('statusWell');
            if (el2 && w) el2.textContent = w.name;
        }
        if (this.renderer) {
            const el3 = document.getElementById('statusDepth');
            if (el3) el3.textContent = `${this.renderer.viewStart?.toFixed(1) || '—'} – ${this.renderer.viewStop?.toFixed(1) || '—'} ft`;
        }
    }

    _updateStatusDepth(start, stop) {
        const el = document.getElementById('statusDepth');
        if (el) el.textContent = `${start.toFixed(1)} – ${stop.toFixed(1)} ft`;
    }

    _updateStatusPoints(count) {
        const el = document.getElementById('statusPoints');
        if (el) el.textContent = `${count.toLocaleString()} pts`;
    }

    // ─── Sprint 26: Context Menu ────────────────────────────────
    showContextMenu(x, y, items) {
        const cm = document.getElementById('contextMenu');
        cm.innerHTML = items.map(item => {
            if (item.separator) return '<div class="context-menu-sep"></div>';
            return `<div class="context-menu-item ${item.danger ? 'danger' : ''}" onclick="${item.action}">
                <i data-lucide="${item.icon || 'circle'}"></i> ${item.label}
            </div>`;
        }).join('');
        cm.style.display = 'block';
        cm.style.left = Math.min(x, window.innerWidth - 220) + 'px';
        cm.style.top = Math.min(y, window.innerHeight - 200) + 'px';
        if (typeof lucide !== 'undefined') lucide.createIcons({ attrs: { 'stroke-width': 1.5 } });
    }

    // ─── Sprint 26: Command Palette ─────────────────────────────
    openCmdPalette() {
        const overlay = document.getElementById('cmdPaletteOverlay');
        overlay.style.display = 'flex';
        const input = document.getElementById('cmdPaletteInput');
        input.value = '';
        input.focus();
        this._renderCmdResults('');
    }

    closeCmdPalette(event) {
        if (event && event.target !== event.currentTarget) return;
        document.getElementById('cmdPaletteOverlay').style.display = 'none';
    }

    filterCmdPalette(query) {
        this._renderCmdResults(query);
    }

    _renderCmdResults(query) {
        const commands = [
            { label: 'Log Viewer', icon: 'activity', action: "app.switchView('viewer')", shortcut: '1' },
            { label: 'Cross Plot', icon: 'scatter-chart', action: "app.switchView('crossplot')", shortcut: '2' },
            { label: 'Pickett Plot', icon: 'chart-no-axes-combined', action: "app.switchView('pickett')", shortcut: '3' },
            { label: 'Petrophysics', icon: 'calculator', action: "app.switchView('petrophysics')", shortcut: '4' },
            { label: 'QC', icon: 'shield-check', action: "app.switchView('qc')", shortcut: '5' },
            { label: 'Statistics', icon: 'bar-chart-3', action: "app.switchView('statistics')", shortcut: '6' },
            { label: 'Correlation', icon: 'split-square-horizontal', action: "app.switchView('correlation')", shortcut: '7' },
            { label: 'Sensitivity', icon: 'git-compare', action: "app.switchView('sensitivity')" },
            { label: 'Facies', icon: 'gem', action: "app.switchView('facies')", shortcut: '9' },
            { label: 'Data Table', icon: 'table', action: "app.switchView('datatable')" },
            { label: 'Map', icon: 'map-pin', action: "app.switchView('map')" },
            { label: 'Dashboard', icon: 'layout-dashboard', action: "app.switchView('dashboard')" },
            { label: 'Matrix Plot', icon: 'grid-3x3', action: "app.switchView('matrix')" },
            { label: 'Audit Trail', icon: 'file-text', action: "app.switchView('audit')" },
            { label: 'Upload LAS', icon: 'upload', action: "app.uploadLAS()" },
            { label: 'Export Report', icon: 'file-down', action: "app.exportReport()" },
            { label: 'Export PNG', icon: 'image', action: "app._exportPNG()" },
            { label: 'Keyboard Shortcuts', icon: 'keyboard', action: "app.openShortcutHelp()", shortcut: '?' },
        ];
        const q = query.toLowerCase();
        const filtered = q ? commands.filter(c => c.label.toLowerCase().includes(q)) : commands;
        const container = document.getElementById('cmdPaletteResults');
        container.innerHTML = filtered.map(c =>
            `<div class="cmd-palette-item" onclick="${c.action}; app.closeCmdPalette()">
                <i data-lucide="${c.icon}"></i> ${c.label}
                ${c.shortcut ? `<span class="shortcut">${c.shortcut}</span>` : ''}
            </div>`
        ).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons({ attrs: { 'stroke-width': 1.5 } });
    }

    // ─── Sprint 26: Audit Trail ─────────────────────────────────
    async loadAuditLog() {
        if (!this.projects.length) return [];
        const pid = this.projects[0]?.id;
        try {
            const resp = await fetch(`/api/audit-log?project_id=${pid}&limit=50`);
            return await resp.json();
        } catch { return []; }
    }

    async _renderAuditPanel() {
        const panel = document.getElementById('auditPanelContent');
        if (!panel) return;
        const entries = await this.loadAuditLog();
        if (!entries.length) {
            panel.innerHTML = `<div class="empty-state">
                <div class="empty-state-icon"><i data-lucide="file-text"></i></div>
                <h3>No Activity Yet</h3>
                <p>Upload LAS files, compute petrophysics, or export data to see the audit trail here.</p>
            </div>`;
            if (typeof lucide !== 'undefined') lucide.createIcons({ attrs: { 'stroke-width': 1.5 } });
            return;
        }
        const iconMap = { upload: 'upload', compute: 'calculator', export: 'download', edit: 'pencil', delete: 'trash-2' };
        panel.innerHTML = `<div class="audit-list">${entries.map(e => `
            <div class="audit-entry">
                <div class="audit-icon ${e.action}"><i data-lucide="${iconMap[e.action] || 'circle'}"></i></div>
                <div class="audit-meta">
                    <div class="audit-action">${e.action.toUpperCase()} ${e.entity_type || ''} ${e.entity_id ? '#' + e.entity_id : ''}</div>
                    <div class="audit-detail">${e.details || ''}</div>
                </div>
                <div class="audit-time">${new Date(e.created_at).toLocaleString()}</div>
            </div>
        `).join('')}</div>`;
        if (typeof lucide !== 'undefined') lucide.createIcons({ attrs: { 'stroke-width': 1.5 } });
    }

    // ─── Sprint 26: Cross-Plot Matrix ───────────────────────────
    async loadCrossPlotMatrix() {
        if (!this.projects.length) return;
        const pid = this.projects[0]?.id;
        const curveX = document.getElementById('matrixCurveX')?.value || 'GR';
        const curveY = document.getElementById('matrixCurveY')?.value || 'RT';
        try {
            const resp = await fetch(`/api/projects/${pid}/crossplot-matrix?curve_x=${curveX}&curve_y=${curveY}`);
            const data = await resp.json();
            this._renderMatrixPlot(data);
        } catch (e) {
            GeoToast.error('Failed to load matrix data');
        }
    }

    _renderMatrixPlot(data) {
        const canvas = document.getElementById('matrixCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width * 2;
        canvas.height = rect.height * 2;
        ctx.scale(2, 2);
        const W = rect.width, H = rect.height;
        const pad = { top: 40, right: 40, bottom: 60, left: 70 };
        const pw = W - pad.left - pad.right;
        const ph = H - pad.top - pad.bottom;

        // Find global ranges
        let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
        for (const w of data.wells) {
            for (let i = 0; i < w.x.length; i++) {
                if (w.x[i] < xMin) xMin = w.x[i];
                if (w.x[i] > xMax) xMax = w.x[i];
                if (w.y[i] < yMin) yMin = w.y[i];
                if (w.y[i] > yMax) yMax = w.y[i];
            }
        }
        if (!isFinite(xMin)) { xMin = 0; xMax = 1; yMin = 0; yMax = 1; }
        const xPad = (xMax - xMin) * 0.05 || 1;
        const yPad = (yMax - yMin) * 0.05 || 1;
        xMin -= xPad; xMax += xPad; yMin -= yPad; yMax += yPad;

        ctx.fillStyle = '#0a0e14';
        ctx.fillRect(0, 0, W, H);

        // Grid
        ctx.strokeStyle = 'rgba(42,52,70,0.5)';
        ctx.lineWidth = 0.5;
        for (let i = 0; i <= 5; i++) {
            const x = pad.left + (pw / 5) * i;
            const y = pad.top + (ph / 5) * i;
            ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + ph); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + pw, y); ctx.stroke();
        }

        // Axes labels
        ctx.fillStyle = '#9aa8b8';
        ctx.font = '12px Geologica';
        ctx.textAlign = 'center';
        ctx.fillText(data.curve_x, pad.left + pw / 2, H - 10);
        ctx.save();
        ctx.translate(16, pad.top + ph / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(data.curve_y, 0, 0);
        ctx.restore();

        // Tick labels
        ctx.font = '10px JetBrains Mono';
        ctx.fillStyle = '#6b7a8d';
        for (let i = 0; i <= 5; i++) {
            const xv = xMin + ((xMax - xMin) / 5) * i;
            const yv = yMin + ((yMax - yMin) / 5) * (5 - i);
            ctx.textAlign = 'center';
            ctx.fillText(xv.toFixed(1), pad.left + (pw / 5) * i, pad.top + ph + 16);
            ctx.textAlign = 'right';
            ctx.fillText(yv.toFixed(2), pad.left - 8, pad.top + (ph / 5) * i + 4);
        }

        // Plot points
        const colors = ['#d4a853', '#4caf7d', '#5b8fb9', '#c75a5a', '#8b6fb0', '#5ba8a0', '#d48a4a', '#a0d45b'];
        const legendEl = document.getElementById('matrixLegend');
        if (legendEl) legendEl.innerHTML = '';
        data.wells.forEach((w, idx) => {
            const color = colors[idx % colors.length];
            ctx.fillStyle = color;
            ctx.globalAlpha = 0.6;
            for (let i = 0; i < w.x.length; i++) {
                const px = pad.left + ((w.x[i] - xMin) / (xMax - xMin)) * pw;
                const py = pad.top + ((yMax - w.y[i]) / (yMax - yMin)) * ph;
                ctx.beginPath();
                ctx.arc(px, py, 2, 0, Math.PI * 2);
                ctx.fill();
            }
            ctx.globalAlpha = 1;
            if (legendEl) {
                legendEl.innerHTML += `<div class="matrix-legend-item"><span class="matrix-legend-dot" style="background:${color}"></span>${w.well_name} (${w.count})</div>`;
            }
        });
    }

    // ─── Sprint 26: Well Report Export ──────────────────────────
    async exportReport() {
        if (!this.currentWell) { GeoToast.warn('Select a well first'); return; }
        GeoLoading.show('Generating report...');
        try {
            const resp = await fetch(`/api/wells/${this.currentWell}/report`);
            const data = await resp.json();
            GeoLoading.hide();
            this._renderReportPreview(data);
        } catch (e) {
            GeoLoading.hide();
            GeoToast.error('Report generation failed');
        }
    }

    _renderReportPreview(data) {
        const w = data.well || {};
        let html = `<div class="report-preview">
            <h1>Well Log Report — ${w.name || 'Unknown'}</h1>
            <p><strong>UWI:</strong> ${w.uwi || '—'} | <strong>Operator:</strong> ${w.operator || '—'} | <strong>Field:</strong> ${w.field_name || '—'} | <strong>Generated:</strong> ${data.generated_at || '—'}</p>`;
        if (data.formation_tops && data.formation_tops.length) {
            html += `<h2>Formation Tops</h2><table><tr><th>Formation</th><th>Depth (${w.depth_unit || 'FT'})</th><th>Lithology</th></tr>`;
            data.formation_tops.forEach(t => {
                html += `<tr><td>${t.formation_name}</td><td>${t.depth?.toFixed(1) || '—'}</td><td>${t.lithology || '—'}</td></tr>`;
            });
            html += '</table>';
        }
        if (data.zones && data.zones.length) {
            html += `<h2>Zones</h2><table><tr><th>Zone</th><th>Top</th><th>Bottom</th><th>Gross (ft)</th></tr>`;
            data.zones.forEach(z => {
                html += `<tr><td>${z.name}</td><td>${z.top_depth?.toFixed(1)}</td><td>${z.bottom_depth?.toFixed(1)}</td><td>${(z.bottom_depth - z.top_depth)?.toFixed(1)}</td></tr>`;
            });
            html += '</table>';
        }
        if (data.curve_summary && data.curve_summary.length) {
            html += `<h2>Curve Summary</h2><table><tr><th>Run</th><th>Curve</th><th>Unit</th><th>Count</th><th>Min</th><th>Max</th><th>Mean</th></tr>`;
            data.curve_summary.forEach(c => {
                html += `<tr><td>${c.run}</td><td>${c.mnemonic}</td><td>${c.unit || ''}</td><td>${c.count?.toLocaleString()}</td><td>${c.min?.toFixed(3) || '—'}</td><td>${c.max?.toFixed(3) || '—'}</td><td>${c.mean?.toFixed(3) || '—'}</td></tr>`;
            });
            html += '</table>';
        }
        if (data.petro_params) {
            html += `<h2>Petrophysics Parameters</h2>`;
            html += `<p><strong>Model:</strong> ${data.petro_params.saturation_model} | <strong>a:</strong> ${data.petro_params.a} | <strong>m:</strong> ${data.petro_params.m} | <strong>n:</strong> ${data.petro_params.n} | <strong>Rw:</strong> ${data.petro_params.rw}</p>`;
            html += `<p><strong>VSH cutoff:</strong> ${data.petro_params.vsh_cutoff} | <strong>PHIE cutoff:</strong> ${data.petro_params.phie_cutoff} | <strong>Sw cutoff:</strong> ${data.petro_params.sw_cutoff}</p>`;
        }
        html += `<div class="report-meta">Generated by GeoLog — Professional Well Log Viewer</div></div>`;
        document.getElementById('reportContent').innerHTML = html;
        document.getElementById('reportModal').style.display = 'flex';
    }

    // ─── Sprint 26: Context Menu for Wells ──────────────────────
    _bindContextMenu() {
        // Right-click on well items in sidebar
        document.addEventListener('contextmenu', (e) => {
            const wellItem = e.target.closest('.well-item');
            if (wellItem) {
                e.preventDefault();
                const wid = parseInt(wellItem.dataset.id);
                this.showContextMenu(e.clientX, e.clientY, [
                    { label: 'Select Well', icon: 'check', action: `app.selectWell(${wid})` },
                    { label: 'Edit Well', icon: 'pencil', action: `app.editWell(${wid})` },
                    { separator: true },
                    { label: 'Upload LAS', icon: 'upload', action: `app.uploadLASForWell(${wid})` },
                    { label: 'Export Report', icon: 'file-down', action: `app.currentWell=${wid}; app.exportReport()` },
                    { label: 'Export Package', icon: 'package', action: `app._exportPackage(${wid})` },
                    { separator: true },
                    { label: 'Delete Well', icon: 'trash-2', action: `app.deleteWell(${wid})`, danger: true },
                ]);
            }
        });
    }

    async _exportPackage(wid) {
        try {
            const resp = await fetch(`/api/wells/${wid}/export-package`);
            const data = await resp.json();
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `well_${wid}_package.json`;
            a.click();
            GeoToast.success('Package exported');
        } catch { GeoToast.error('Export failed'); }
    }

    async uploadLASForWell(wid) {
        // Upload LAS to specific well
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.las';
        input.onchange = async () => {
            const file = input.files[0];
            if (!file) return;
            GeoLoading.show(`Uploading ${file.name}...`);
            const fd = new FormData();
            fd.append('file', file);
            try {
                const resp = await fetch(`/api/wells/${wid}/upload-las`, { method: 'POST', body: fd });
                if (resp.ok) {
                    GeoToast.success(`Uploaded to well #${wid}`);
                    await this.loadProjects();
                } else {
                    GeoToast.error('Upload failed');
                }
            } catch { GeoToast.error('Upload failed'); }
            GeoLoading.hide();
        };
        input.click();
    }

    async editWell(wid) {
        await this.selectWell(wid);
        this.editCurrentWell();
    }

    deleteWell(wid) {
        if (!confirm('Delete this well and all its data?')) return;
        fetch(`/api/wells/${wid}`, { method: 'DELETE' }).then(() => {
            GeoToast.success('Well deleted');
            this.loadProjects();
        });
    }

}
// Initialize
const app = new GeoLogApp();

// ─── Keyboard Shortcuts ────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    // Don't trigger if typing in input/textarea
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

    const views = ['viewer', 'crossplot', 'pickett', 'mnplot', 'petrophysics', 'qc', 'correlation', 'statistics', 'sensitivity', 'comparison', 'striplog', 'facies', 'tools', 'probability', 'moveable', 'dipplot', 'buckles', 'hingle', 'calculator', 'datatable', 'topsmgmt', 'formation', 'batch', 'map', 'dashboard', 'matrix', 'audit'];

    switch (e.key) {
        case '1': case '2': case '3': case '4':
        case '5': case '6': case '7': case '8':
            e.preventDefault();
            app.switchView(views[parseInt(e.key) - 1]);
            break;
        case 'ArrowUp':
            if (!app.renderer) return;
            e.preventDefault();
            {
                const range = app.renderer.viewStop - app.renderer.viewStart;
                const shift = range * 0.25;
                app.renderer.setView(app.renderer.viewStart - shift, app.renderer.viewStop - shift);
            }
            break;
        case 'ArrowDown':
            if (!app.renderer) return;
            e.preventDefault();
            {
                const range = app.renderer.viewStop - app.renderer.viewStart;
                const shift = range * 0.25;
                app.renderer.setView(app.renderer.viewStart + shift, app.renderer.viewStop + shift);
            }
            break;
        case '+': case '=':
            if (!app.renderer) return;
            e.preventDefault();
            {
                const mid = (app.renderer.viewStart + app.renderer.viewStop) / 2;
                const newRange = (app.renderer.viewStop - app.renderer.viewStart) * 0.75;
                app.renderer.setView(mid - newRange / 2, mid + newRange / 2);
            }
            break;
        case '-':
            if (!app.renderer) return;
            e.preventDefault();
            {
                const mid = (app.renderer.viewStart + app.renderer.viewStop) / 2;
                const newRange = (app.renderer.viewStop - app.renderer.viewStart) * 1.33;
                app.renderer.setView(mid - newRange / 2, mid + newRange / 2);
            }
            break;
        case 'Escape':
            if (GeoModal._resolve) { GeoModal.close(); }
            app.closeShortcutHelp();
            app.closeCmdPalette();
            break;
        case '?':
            e.preventDefault();
            app.openShortcutHelp();
            break;
        case 'k':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                app.openCmdPalette();
            }
            break;
        case 'z':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                app.undoZone();
            }
            break;
        case 'y':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                app.redoZone();
            }
            break;
        case 'r':
            if (e.ctrlKey || e.metaKey) return;
            e.preventDefault();
            if (app.renderer) app.renderer.render();
            GeoToast.info('Refreshed');
            break;
    }
});
