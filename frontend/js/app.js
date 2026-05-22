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

        this.init();
    }

    async init() {
        this.renderer = new LogRenderer('logCanvas');
        this._bindUI();
        await this.loadCurveConfig();
        await this.loadProjects();
        if (typeof lucide !== 'undefined') lucide.createIcons();
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
    }

    // ─── API ─────────────────────────────────────────────────
    async _api(path, opts = {}) {
        const resp = await fetch('/api' + path, {
            headers: { 'Content-Type': 'application/json', ...opts.headers },
            ...opts,
        });
        if (!resp.ok) throw new Error(`API error: ${resp.status}`);
        if (resp.status === 204) return null;
        return resp.json();
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

            if (well.log_runs && well.log_runs.length > 0) {
                this.currentLogRun = well.log_runs[0];
                this._populateLogRunSelector(well.log_runs, this.currentLogRun.id);
                await this._loadCurveData();
                await this._loadFormationTops();
            } else {
                this.currentLogRun = null;
                this._populateLogRunSelector([], null);
            }

            this._renderWellHeader(well);
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
            this._renderWellHeader(well);
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

        if (!wellAId || !wellBId) {
            ctx.fillStyle='#8b949e'; ctx.font='14px DM Sans'; ctx.fillText('Select wells', 40, 40); return;
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

        const depthA = da.DEPTH || [], depthB = (db.DEPTH || []).map(d => d + shift);
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
        this.corrLastRender = { m, w, h, xMin, xMax, yMin, yMax, shift, waName: wa.name, wbName: wb.name };

        // Draw marker ties
        this.corrMarkers.forEach((mk, idx) => {
            const xA = sx(mk.aDepth);
            const xB = sx(mk.bDepth + shift);
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

    startMarkerPick() {
        this.corrPickMode = true;
        this._corrPickTemp = null;
        const info = document.getElementById('corrInfo');
        if (info) info.textContent = 'Pick mode: click depth for Well A, then click depth for Well B';
    }

    clearMarkers() {
        this.corrMarkers = [];
        const info = document.getElementById('corrInfo');
        if (info) info.textContent = 'Markers cleared';
        this._renderCorrelationMarkerTable();
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
        const { m, w, xMin, xMax, shift } = this.corrLastRender;
        if (x < m.left || x > m.left + w) return;

        const depth = xMin + ((x - m.left) / w) * (xMax - xMin);
        const info = document.getElementById('corrInfo');

        if (this._corrPickTemp == null) {
            this._corrPickTemp = depth;
            if (info) info.textContent = `Marker A picked @ ${depth.toFixed(1)} ft. Now click marker B depth.`;
        } else {
            const aDepth = this._corrPickTemp;
            const bDepth = depth - shift;
            this.corrMarkers.push({ aDepth, bDepth });
            this._corrPickTemp = null;
            const localShift = aDepth - bDepth;
            if (info) info.textContent = `Marker tie added. Local shift Δ=${localShift.toFixed(1)} ft`;
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

    async addFormationTop() {
        if (!this.currentWell) return;
        const r = await GeoModal.show({ title: 'Add Formation Top', fields: [
            { id: 'name', label: 'Formation Name', placeholder: 'e.g. Top Reservoir' },
            { id: 'depth', label: 'Depth (ft)', type: 'number', step: '0.1', placeholder: '5000.0' },
            { id: 'color', label: 'Color', type: 'color', value: '#f0883e' },
            { id: 'lithology', label: 'Lithology (optional)', placeholder: 'e.g. Sandstone' },
        ]});
        if (!r?.name || isNaN(parseFloat(r.depth))) return;
        const name = r.name, depth = parseFloat(r.depth), color = r.color || '#f0883e', lithology = r.lithology || '';
        try {
            await this._api(`/wells/${this.currentWell.id}/tops`, {
                method: 'POST',
                body: JSON.stringify({ formation_name: name, depth, color, lithology, depth_unit: 'FT' }),
            });
            await this._loadFormationTops();
        } catch (e) { GeoToast.error('Failed to add top: ' + e.message); }
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
        const zones = [...(this.renderer.zones || []), { name, top, bottom }];
        this.renderer.setZones(zones);
        this._renderZonesList();
    }

    removeZone(index) {
        const zones = [...(this.renderer.zones || [])];
        zones.splice(index, 1);
        this.renderer.setZones(zones);
        this._renderZonesList();
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
                <button class="btn-icon-sm" onclick="app.removeZone(${i})" title="Remove">
                    <i data-lucide="x"></i>
                </button>
            </div>
        `).join('');
        if (typeof lucide !== 'undefined') lucide.createIcons();
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

        // Calculate Sw (Archie)
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

            // Archie Sw
            let swVal = 1;
            if (rtVal > 0 && phieVal > 0.01) {
                swVal = Math.pow(a / (phieVal ** m * rtVal / rw), 1 / n);
                swVal = Math.max(0, Math.min(1, swVal));
            }

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
                <h4>Archie Parameters</h4>
                <div class="petro-stat"><span>a:</span> <strong>${a}</strong></div>
                <div class="petro-stat"><span>m:</span> <strong>${m}</strong></div>
                <div class="petro-stat"><span>n:</span> <strong>${n}</strong></div>
                <div class="petro-stat"><span>Rw:</span> <strong>${rw}</strong></div>
            </div>
        `;

        // Refresh viewer
        this.renderer.render();
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

        panel.innerHTML = `
            <div class="petro-summary" style="margin-bottom:10px">
                <div class="petro-stat"><span>Reliability Summary:</span> <strong>HIGH ${highCount} • MEDIUM ${medCount} • LOW ${lowCount}</strong></div>
                ${smallSampleWarn}
                <div class="petro-stat"><span>Rules:</span> <strong>LOW if missing>20% or outlier>8%</strong></div>
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
}

// Initialize
const app = new GeoLogApp();
