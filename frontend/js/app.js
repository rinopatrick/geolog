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
        this._corrTopOverlay = { a: [], b: [] };
        this.corrShowTops = true;
        this.corrSelectedTop = null;
        this._petroCache = null;
        this.permResults = null;
        this.zoneUndoStack = [];
        this.zoneRedoStack = [];
        this._undoStack = [];
        this._redoStack = [];
        this._maxUndoEntries = 50;
        this.performanceMode = localStorage.getItem('geolog_performance_mode') === '1';
        this.maxPoints = parseInt(localStorage.getItem('geolog_max_points') || '3000', 10);
        this._searchDebounceTimer = null;
        this._jobMonitorTimer = null;
        this.currentRole = (localStorage.getItem('geolog_active_role') || 'admin').toLowerCase();
        this.authToken = localStorage.getItem('geolog_auth_token') || '';
        this.jobIds = JSON.parse(localStorage.getItem('geolog_job_ids') || '[]');
        this.dstData = [];
        this.rftData = [];
        this.rftGradientAnalysis = null;
        this.productionData = [];
        this.productionDecline = null;
        this.apiTimeoutMs = 30000;
        this._apiPendingRequests = new Map();
        this.curveRangeCache = new Map();
        this._curveLoadDebounceTimer = null;
        this._viewportPaddingFactor = 0.5;
        this._suppressViewportLoad = false;
        this._showLithTrack = false;
        this._lithologyData = null;
        this._lastRwEstimation = null;
        this.completionData = [];
        this.showCompletionTrack = true;
        this.workflowTemplates = [];
        this.depthSync = { enabled: true, activeDepth: null, source: null };
        this._seismicSyncCtx = null;
        this._imageSyncCtx = null;

        this.overlayState = {
            enabled: false,
            runAId: null,
            runBId: null,
            curve: 'GR',
            color: '#ff3b30',
            opacity: 0.5,
            showDifference: false,
        };
        this.overlayRunCache = new Map();

        this.curveEditState = {
            enabled: false,
            mnemonic: null,
            originals: {},
            selected: [],
            edits: {},
            history: [],
            nextId: 1,
        };

        this.lqcState = {
            result: null,
            originalCurve: null,
            correctedCurve: null,
            activeMnemonic: null,
            showCorrected: false,
        };

        this.init();
    }

    _pushUndo(action, data) {
        this._undoStack.push({ action, data, timestamp: new Date().toISOString() });
        if (this._undoStack.length > this._maxUndoEntries) this._undoStack.shift();
        this._redoStack = [];
        this._updateUndoRedoButtons();
    }

    _updateUndoRedoButtons() {
        const undoBtn = document.getElementById('btnUndo');
        const redoBtn = document.getElementById('btnRedo');
        if (undoBtn) undoBtn.disabled = this._undoStack.length === 0;
        if (redoBtn) redoBtn.disabled = this._redoStack.length === 0;
    }

    async undo() {
        if (!this._undoStack.length) return GeoToast.warn('Nothing to undo');
        const entry = this._undoStack.pop();
        try {
            switch (entry.action) {
                case 'add_top': {
                    const topId = entry?.data?.top_id;
                    if (!topId) throw new Error('Missing top id for undo');
                    await this._api(`/tops/${topId}`, { method: 'DELETE' });
                    await this._loadFormationTops();
                    break;
                }
                case 'add_annotation': {
                    const annId = entry?.data?.annotation_id;
                    if (!annId) throw new Error('Missing annotation id for undo');
                    await this._api(`/annotations/${annId}`, { method: 'DELETE' });
                    await this.loadAnnotations();
                    break;
                }
                case 'add_zone': {
                    if (!this.currentWell) throw new Error('No active well for zone undo');
                    const zonesBefore = Array.isArray(entry?.data?.zones_before) ? entry.data.zones_before : null;
                    if (zonesBefore) {
                        this.renderer?.setZones(JSON.parse(JSON.stringify(zonesBefore)));
                        this._renderZonesList();
                        await this._saveZones();
                    } else if (entry?.data?.zone_id && this.renderer) {
                        const zones = (this.renderer.zones || []).filter(z => z.id !== entry.data.zone_id);
                        this.renderer.setZones(zones);
                        this._renderZonesList();
                        await this._saveZones();
                    } else {
                        throw new Error('Missing zone data for undo');
                    }
                    break;
                }
                default:
                    throw new Error(`Undo not implemented for action: ${entry.action}`);
            }
            this._redoStack.push(entry);
            if (this._redoStack.length > this._maxUndoEntries) this._redoStack.shift();
            this._updateUndoRedoButtons();
            GeoToast.info('Undo applied');
        } catch (e) {
            this._undoStack.push(entry);
            this._updateUndoRedoButtons();
            GeoToast.error('Undo failed: ' + (e.message || e));
        }
    }

    async redo() {
        if (!this._redoStack.length) return GeoToast.warn('Nothing to redo');
        const entry = this._redoStack.pop();
        try {
            switch (entry.action) {
                case 'add_top': {
                    const payload = entry?.data?.payload;
                    const wellId = entry?.data?.well_id;
                    if (!payload || !wellId) throw new Error('Missing top payload for redo');
                    const created = await this._api(`/wells/${wellId}/tops`, {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                    if (created?.id) entry.data.top_id = created.id;
                    await this._loadFormationTops();
                    break;
                }
                case 'add_annotation': {
                    const payload = entry?.data?.payload;
                    const wellId = entry?.data?.well_id;
                    if (!payload || !wellId) throw new Error('Missing annotation payload for redo');
                    const created = await this._api(`/wells/${wellId}/annotations`, {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                    if (created?.id) entry.data.annotation_id = created.id;
                    await this.loadAnnotations();
                    break;
                }
                case 'add_zone': {
                    if (!this.currentWell) throw new Error('No active well for zone redo');
                    const zonesAfter = Array.isArray(entry?.data?.zones_after) ? entry.data.zones_after : null;
                    const zonePayload = entry?.data?.zone_payload;
                    if (zonesAfter) {
                        this.renderer?.setZones(JSON.parse(JSON.stringify(zonesAfter)));
                        this._renderZonesList();
                        await this._saveZones();
                    } else if (zonePayload && this.renderer) {
                        const zones = [...(this.renderer.zones || []), zonePayload];
                        this.renderer.setZones(zones);
                        this._renderZonesList();
                        await this._saveZones();
                    } else {
                        throw new Error('Missing zone data for redo');
                    }
                    break;
                }
                default:
                    throw new Error(`Redo not implemented for action: ${entry.action}`);
            }
            this._undoStack.push(entry);
            if (this._undoStack.length > this._maxUndoEntries) this._undoStack.shift();
            this._updateUndoRedoButtons();
            GeoToast.info('Redo applied');
        } catch (e) {
            this._redoStack.push(entry);
            this._updateUndoRedoButtons();
            GeoToast.error('Redo failed: ' + (e.message || e));
        }
    }

    async init() {
        this.renderer = new LogRenderer('logCanvas');
        this.renderer.onViewChanged = (start, stop) => this._onViewportChanged(start, stop);
        this._bindUI();
        await this.loadCurveConfig();
        await this.loadWorkflowTemplates();
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
        this._restoreUIPreferences();
        this._applyRoleGates();
        this._showFirstRunWelcome();
        this._bindContextMenu();
        this._updateUndoRedoButtons();
        
        // Sprint 31: Professional features init
        this._initProKeyboard();
        this._initFavorites();
        this._initThumbnailPreview();
        this._initDoubleClickTop();
        this._wireRendererCallbacks();
    }

    _bindUI() {
        // Navigation
        document.querySelectorAll('.nav-btn[data-view]').forEach(btn => {
            btn.addEventListener('click', () => {
                this.switchView(btn.dataset.view);
                this._closeAllNavGroups();
            });
        });
        this._bindNavGroups();

        // Scale selector
        const scaleSelect = document.getElementById('scaleSelect');
        if (scaleSelect) {
            scaleSelect.addEventListener('change', () => {
                const scale = parseInt(scaleSelect.value);
                this.renderer.scale = scale;
                localStorage.setItem('geolog_scale', String(scale));
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
                    localStorage.setItem('geolog_depth_top', String(start));
                    localStorage.setItem('geolog_depth_bottom', String(stop));
                }
            };
            topInput.addEventListener('change', applyDepth);
            bottomInput.addEventListener('change', applyDepth);
        }

        // Search
        const searchInput = document.getElementById('wellSearch');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(this._searchDebounceTimer);
                const q = searchInput.value;
                this._searchDebounceTimer = setTimeout(() => this._filterWells(q), 120);
            });
        }

        const perfToggle = document.getElementById('performanceModeToggle');
        const maxPointsInput = document.getElementById('maxPointsInput');
        if (perfToggle) {
            perfToggle.checked = this.performanceMode;
            perfToggle.addEventListener('change', async () => {
                this.performanceMode = perfToggle.checked;
                localStorage.setItem('geolog_performance_mode', this.performanceMode ? '1' : '0');
                await this._loadCurveData();
            });
        }
        if (maxPointsInput) {
            if (Number.isFinite(this.maxPoints) && this.maxPoints > 0) maxPointsInput.value = String(this.maxPoints);
            maxPointsInput.addEventListener('change', async () => {
                const v = Math.max(500, Math.min(20000, parseInt(maxPointsInput.value || '3000', 10)));
                this.maxPoints = Number.isFinite(v) ? v : 3000;
                maxPointsInput.value = String(this.maxPoints);
                localStorage.setItem('geolog_max_points', String(this.maxPoints));
                if (this.performanceMode) await this._loadCurveData();
            });
        }

        ['lithGrMin', 'lithGrMax', 'lithMethod'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', () => {
                this._lithologyData = null;
                if (this._showLithTrack) this.toggleLithTrack(true);
            });
        });

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

        // Correlation canvas pick/drag handler
        document.getElementById('correlationCanvas')?.addEventListener('click', (ev) => this._onCorrelationCanvasClick(ev));
        document.getElementById('correlationCanvas')?.addEventListener('mousedown', (ev) => this._onCorrelationCanvasMouseDown(ev));
        document.getElementById('correlationCanvas')?.addEventListener('mousemove', (ev) => this._onCorrelationCanvasMouseMove(ev));
        window.addEventListener('mouseup', (ev) => this._onCorrelationCanvasMouseUp(ev));
        document.getElementById('logCanvas')?.addEventListener('click', (e) => {
            if (this.curveEditState.enabled) {
                this.onCurveEditCanvasClick(e);
                return;
            }
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
        document.getElementById('corrShowTops')?.addEventListener('click', () => this.toggleCorrelationTops());

        document.getElementById('editModeToggle')?.addEventListener('click', () => this.toggleEditMode());
        document.getElementById('overlayToggleBtn')?.addEventListener('click', () => this.toggleOverlayPanel());
        document.getElementById('overlayRunA')?.addEventListener('change', (e) => this.onOverlayControlChange('runAId', parseInt(e.target.value || '0', 10) || null));
        document.getElementById('overlayRunB')?.addEventListener('change', (e) => this.onOverlayControlChange('runBId', parseInt(e.target.value || '0', 10) || null));
        document.getElementById('overlayCurve')?.addEventListener('change', (e) => this.onOverlayControlChange('curve', (e.target.value || '').toUpperCase()));
        document.getElementById('overlayColor')?.addEventListener('input', (e) => this.onOverlayControlChange('color', e.target.value || '#ff3b30'));
        document.getElementById('overlayOpacity')?.addEventListener('input', (e) => {
            const val = Math.max(0.05, Math.min(1, (parseInt(e.target.value || '50', 10) || 50) / 100));
            this.onOverlayControlChange('opacity', val);
            const lbl = document.getElementById('overlayOpacityLabel');
            if (lbl) lbl.textContent = `${Math.round(val * 100)}%`;
        });
        document.getElementById('overlayShowDiff')?.addEventListener('change', (e) => this.onOverlayControlChange('showDifference', !!e.target.checked));
        document.getElementById('overlayClearBtn')?.addEventListener('click', () => this.clearOverlay());
        document.getElementById('completionTrackToggle')?.addEventListener('change', (e) => this.toggleCompletionTrack(!!e.target.checked));
        document.getElementById('completionCsvFileInput')?.addEventListener('change', () => this.uploadCompletionCSV());
        document.getElementById('editCurveSelect')?.addEventListener('change', (e) => this.setEditCurve(e.target.value));
        document.getElementById('editSaveBtn')?.addEventListener('click', () => this.saveCurveEdits());
        document.getElementById('editCancelBtn')?.addEventListener('click', () => this.cancelCurveEdits());
        document.getElementById('editValueApplyBtn')?.addEventListener('click', () => this.applyEditValueInput());
        document.getElementById('editValueInput')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.applyEditValueInput();
        });
        document.addEventListener('keydown', (e) => {
            if (!this.curveEditState.enabled) return;
            if (e.key === 'Delete' || e.key === 'Backspace') {
                e.preventDefault();
                this.deleteSelectedEditPoints();
            }
        });

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
                    const resp = await fetch(`/api/wells/${this.currentWell.id}/upload-las`, {
                        method: 'POST',
                        body: formData,
                        headers: this._authHeaders(),
                    });
                    if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
                    const result = await resp.json();
                    this._applyUploadedLASVersion(result);
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
        document.getElementById('productionPanel').style.display = view === 'production' ? 'block' : 'none';
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
        document.getElementById('tornadoPanel').style.display = view === 'tornado' ? 'block' : 'none';
        document.getElementById('vclmodelsPanel').style.display = view === 'vclmodels' ? 'block' : 'none';
        document.getElementById('corecalPanel').style.display = view === 'corecal' ? 'block' : 'none';
        document.getElementById('corescalPanel').style.display = view === 'corescal' ? 'block' : 'none';
        document.getElementById('geomechanicsPanel').style.display = view === 'geomechanics' ? 'block' : 'none';
        document.getElementById('qcautofixPanel').style.display = view === 'qcautofix' ? 'block' : 'none';
        document.getElementById('seismicPanel').style.display = view === 'seismic' ? 'block' : 'none';
        document.getElementById('imagelogPanel').style.display = view === 'imagelog' ? 'block' : 'none';
        document.getElementById('multiwellPanel').style.display = view === 'multiwell' ? 'block' : 'none';
        document.getElementById('formationtesterPanel').style.display = view === 'formationtester' ? 'block' : 'none';
        document.getElementById('analogsPanel').style.display = view === 'analogs' ? 'block' : 'none';
        document.getElementById('usersPanel').style.display = view === 'users' ? 'block' : 'none';
        document.getElementById('jobmonitorPanel').style.display = view === 'jobmonitor' ? 'block' : 'none';
        document.getElementById('advancedqcPanel').style.display = view === 'advancedqc' ? 'block' : 'none';
        document.getElementById('zonationPanel').style.display = view === 'zonation' ? 'block' : 'none';
        document.getElementById('unitsPanel').style.display = view === 'units' ? 'block' : 'none';
        document.getElementById('templatesPanel').style.display = view === 'templates' ? 'block' : 'none';
        document.getElementById('reportBuilderPanel').style.display = view === 'reportbuilder' ? 'block' : 'none';

        // Sprint 26: Update status bar + trigger panel-specific loads
        this._updateStatusBar(view);
        if (view === 'matrix') this.loadCrossPlotMatrix();
        if (view === 'audit') this._renderAuditPanel();
        if (view === 'users') this.loadUsers();
        if (view === 'jobmonitor') this._refreshJobMonitor();
        if (view === 'seismic') this.loadSeismicLines();
        if (view === 'reportbuilder') this.loadReportTemplates();

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
        if (view === 'tools') { this._initToolsPanel(); this.refreshJobs(); }
        if (view === 'production') { this.loadProduction(); this._initProductionCSVUpload(); }
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
        if (view === 'advancedqc' && this.currentWell) this._initAdvancedQC();
        if (view === 'zonation' && this.currentWell) this._initZonation();
        if (view === 'units' && this.currentWell) this._initUnits();
        if (view === 'templates' && this.currentWell) this._initTemplates();
        if (view === 'corescal' && this.currentWell && window.CoreScalView) CoreScalView.load();
        if (view === 'geomechanics' && this.currentWell && window.GeomechanicsView) GeomechanicsView.load();
        if (view === 'imagelog' && this.currentWell && window.ImageLogView) ImageLogView.load();
        if (view === 'multiwell') { if (typeof MultiWellView !== 'undefined') MultiWellView.load(); }
        if (view === 'formationtester') { if (typeof FormationTesterView !== 'undefined') FormationTesterView.run(); }
        localStorage.setItem('geolog_last_view', view);
    }

    _bindNavGroups() {
        const groups = Array.from(document.querySelectorAll('.nav-group'));
        groups.forEach(group => {
            group.addEventListener('toggle', () => {
                if (!group.open) return;
                groups.forEach(other => {
                    if (other !== group) other.open = false;
                });
            });
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.topbar-nav') && !e.target.closest('.btn-group-dropdown')) {
                this._closeAllNavGroups();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this._closeAllNavGroups();
        });
    }

    _closeAllNavGroups() {
        document.querySelectorAll('.nav-group').forEach(g => { g.open = false; });
        document.querySelectorAll('.btn-group-dropdown.open').forEach(d => d.classList.remove('open'));
    }

    _restoreUIPreferences() {
        const savedScale = parseInt(localStorage.getItem('geolog_scale') || '', 10);
        if (Number.isFinite(savedScale)) {
            const scaleSelect = document.getElementById('scaleSelect');
            if (scaleSelect) scaleSelect.value = String(savedScale);
            if (this.renderer) this.renderer.scale = savedScale;
        }

        const top = parseFloat(localStorage.getItem('geolog_depth_top') || '');
        const bottom = parseFloat(localStorage.getItem('geolog_depth_bottom') || '');
        if (Number.isFinite(top)) {
            const topInput = document.getElementById('depthTop');
            if (topInput) topInput.value = String(top);
        }
        if (Number.isFinite(bottom)) {
            const bottomInput = document.getElementById('depthBottom');
            if (bottomInput) bottomInput.value = String(bottom);
        }

        const roleSelect = document.getElementById('activeRoleSelect');
        if (roleSelect) roleSelect.value = this.currentRole;

        const lastView = localStorage.getItem('geolog_last_view');
        if (lastView) this.switchView(lastView);
    }

    _applyRoleGates() {
        const role = String(this.currentRole || 'viewer').toLowerCase();
        const rank = { viewer: 1, interpreter: 2, admin: 3 };
        const roleByAction = {
            // interpreter/admin actions
            lockTemplateSignature: 'interpreter,admin',
            unlockTemplateSignature: 'interpreter,admin',
            saveCorrelationSettings: 'interpreter,admin',
            savePetroParams: 'interpreter,admin',
            applyWorkflowTemplate: 'interpreter,admin',
            runAutoDepthMatch: 'interpreter,admin',
            runSplice: 'interpreter,admin',
            saveDepthShift: 'interpreter,admin',
            // interpreter-only actions
            runSensitivity: 'interpreter',
            runElectrofacies: 'interpreter',
            runElectrofaciesAsync: 'interpreter',
            runDualWater: 'interpreter',
            runMultimineral: 'interpreter',
            runPermeabilityMulti: 'interpreter',
            runVclEnhanced: 'interpreter',
            computeSwMultiEquation: 'interpreter',
        };

        document.querySelectorAll('button[onclick], [data-role-required]').forEach((el) => {
            let requiredSpec = String(el.getAttribute('data-role-required') || '').trim();
            if (!requiredSpec) {
                const onclick = String(el.getAttribute('onclick') || '');
                const m = onclick.match(/app\.(\w+)\s*\(/);
                const action = m?.[1];
                if (action && roleByAction[action]) {
                    requiredSpec = roleByAction[action];
                    el.setAttribute('data-role-required', requiredSpec);
                    if (!el.getAttribute('title')) {
                        const pretty = requiredSpec.split(',').map(s => s.trim()).join(' or ');
                        el.setAttribute('title', `Role required: ${pretty[0].toUpperCase()}${pretty.slice(1)}`);
                    }
                }
            }
            if (!requiredSpec) return;

            const required = requiredSpec
                .split(',')
                .map(s => s.trim().toLowerCase())
                .filter(Boolean);
            const allowed = required.length === 0 || required.some(r => (rank[role] || 0) >= (rank[r] || 99));
            el.disabled = !allowed;
            el.style.opacity = allowed ? '' : '0.55';
            el.style.cursor = allowed ? '' : 'not-allowed';
            const baseTitle = el.getAttribute('title') || '';
            const cleanTitle = baseTitle.replace(/ \(current: .*\)$/,'');
            if (!allowed && cleanTitle) {
                el.setAttribute('title', `${cleanTitle} (current: ${role})`);
            } else if (cleanTitle) {
                el.setAttribute('title', cleanTitle);
            }
        });
    }

    _authHeaders() {
        const headers = { 'X-User-Role': this.currentRole || 'viewer' };
        if (this.authToken) {
            headers['Authorization'] = `Bearer ${this.authToken}`;
        }
        return headers;
    }

    setAuthToken(token) {
        this.authToken = (token || '').trim();
        if (this.authToken) {
            localStorage.setItem('geolog_auth_token', this.authToken);
        } else {
            localStorage.removeItem('geolog_auth_token');
        }
    }

    setActiveRole(role) {
        const r = String(role || 'viewer').toLowerCase();
        this.currentRole = r;
        localStorage.setItem('geolog_active_role', r);
        this._applyRoleGates();
        GeoToast.info(`Active role: ${r}`);
    }

    _updateWorkflowStrip() {
        const strip = document.getElementById('workflowStrip');
        if (!strip) return;
        const steps = strip.querySelectorAll('.wf-step');
        if (!steps.length) return;

        const hasWell = !!this.currentWell;
        const hasRuns = hasWell && this.currentWell.log_runs?.length > 0;
        const hasTops = hasWell && this.formationTops?.length > 0;
        const hasZones = hasWell && this.renderer?.zones?.length > 0;

        // Reset all
        steps.forEach(s => { s.classList.remove('active', 'done'); });

        if (!hasWell) {
            steps[0]?.classList.add('active');
            return;
        }
        if (!hasRuns) { steps[0]?.classList.add('active'); return; }
        steps[0]?.classList.add('done');

        if (!hasTops) { steps[1]?.classList.add('active'); return; }
        steps[1]?.classList.add('done');

        if (!hasZones) { steps[2]?.classList.add('active'); return; }
        steps[2]?.classList.add('done');

        // Interpret + Export available
        steps[3]?.classList.add('active');
        steps[4]?.classList.add('active');
    }

    async runSmokeRegression() {
        try {
            const res = await this._api('/regression/smoke');
            const ok = !!res.ok;
            const failed = (res.checks || []).filter(c => !c.ok).map(c => c.name);
            if (ok) GeoToast.success('Smoke regression: PASS');
            else GeoToast.error(`Smoke regression: FAIL (${failed.join(', ')})`);
            const host = document.getElementById('regressionResult');
            if (host) {
                host.innerHTML = `<pre>${escapeHtml(JSON.stringify(res, null, 2))}</pre>`;
            }
        } catch (e) {
            GeoToast.error('Smoke regression error: ' + e.message);
        }
    }

    async _refreshJobMonitor() {
        try {
            const res = await this._api('/jobs');
            this._renderJobMonitor(res.jobs || []);
            // Auto-poll every 3s if any job is still running
            clearInterval(this._jobMonitorTimer);
            const hasActive = (res.jobs || []).some(j => j.status === 'queued' || j.status === 'running');
            if (hasActive) {
                this._jobMonitorTimer = setInterval(() => this._refreshJobMonitor(), 3000);
            }
        } catch (e) {
            const host = document.getElementById('jobMonitorBody');
            if (host) host.innerHTML = `<p style="color:var(--danger)">Error: ${escapeHtml(String(e.message || e))}</p>`;
        }
    }

    _renderJobMonitor(jobs) {
        const host = document.getElementById('jobMonitorBody');
        if (!host) return;
        if (!jobs.length) {
            host.innerHTML = '<p style="color:var(--text-muted)">No background jobs yet. Use async endpoints (synthetic-seismogram-async, electrofacies-async, batch-petro-async) to queue jobs.</p>';
            return;
        }
        const statusColors = { queued: '#d29922', running: '#58a6ff', done: '#3fb950', failed: '#f85149' };
        const statusIcons = { queued: '⏳', running: '🔄', done: '✅', failed: '❌' };
        let html = '<table style="width:100%;border-collapse:collapse;font-size:13px">';
        html += '<thead><tr style="border-bottom:1px solid var(--border);text-align:left">';
        html += '<th style="padding:8px">Status</th><th>Type</th><th>ID</th><th>Created</th><th>Finished</th><th>Error</th>';
        html += '</tr></thead><tbody>';
        for (const j of jobs) {
            const color = statusColors[j.status] || '#8b949e';
            const icon = statusIcons[j.status] || '❓';
            html += `<tr style="border-bottom:1px solid var(--border-light)">`;
            html += `<td style="padding:8px;color:${color};font-weight:600">${icon} ${j.status}</td>`;
            html += `<td style="padding:8px">${j.type || '-'}</td>`;
            html += `<td style="padding:8px;font-family:var(--font-mono);font-size:11px">${j.id}</td>`;
            html += `<td style="padding:8px">${j.created_at ? new Date(j.created_at).toLocaleTimeString() : '-'}</td>`;
            html += `<td style="padding:8px">${j.finished_at ? new Date(j.finished_at).toLocaleTimeString() : '-'}</td>`;
            html += `<td style="padding:8px;color:var(--danger);max-width:200px;overflow:hidden;text-overflow:ellipsis">${j.error || ''}</td>`;
            html += '</tr>';
        }
        html += '</tbody></table>';
        host.innerHTML = html;
    }

    // ─── API ─────────────────────────────────────────────────
    _api(path, opts = {}) { return GeoAPI._api(this, path, opts); }
    _apiExecute(path, opts = {}) { return GeoAPI._apiExecute(this, path, opts); }
    _apiBlob(path, opts = {}) { return GeoAPI._apiBlob(this, path, opts); }



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
            this.overlayRunCache.clear();
            this.overlayState.runAId = null;
            this.overlayState.runBId = null;

            // Highlight in sidebar
            document.querySelectorAll('.well-item').forEach(el => el.classList.remove('active'));
            document.querySelector(`.well-item[data-id="${wellId}"]`)?.classList.add('active');

            this.loadPetroParams();
            this.renderTemplateCards();
            this._initBulkUpload();
            this._initCSVUpload();
            if (well.log_runs && well.log_runs.length > 0) {
                this.currentLogRun = this._normalizeLogRunVersion(well.log_runs[0]);
                this._populateLogRunSelector(well.log_runs, this.currentLogRun.id);
                // Auto-populate depth inputs on initial well load
                const topIn = document.getElementById('depthTop');
                const botIn = document.getElementById('depthBottom');
                if (topIn && this.currentLogRun.start_depth != null) topIn.value = this.currentLogRun.start_depth;
                if (botIn && this.currentLogRun.stop_depth != null) botIn.value = this.currentLogRun.stop_depth;
                await this._loadCurveData();
                await this._loadFormationTops();
                await this._loadZones();
            } else {
                this.currentLogRun = null;
                this._populateLogRunSelector([], null);
            }

            this._renderWellHeader(well);
            localStorage.setItem('geolog_last_well', wellId);
            this._updateWorkflowStrip();

            // Connect collaboration WebSocket
            if (typeof CollabManager !== 'undefined') {
                CollabManager.connect(wellId, null, 'User');
                // Send cursor position on view change
                if (this.renderer) {
                    const origOnViewChanged = this.renderer.onViewChanged;
                    this.renderer.onViewChanged = (start, stop) => {
                        if (origOnViewChanged) origOnViewChanged(start, stop);
                        const mid = (start + stop) / 2;
                        CollabManager.sendCursorMove(mid);
                    };
                }
            }
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
            this.currentLogRun = this._normalizeLogRunVersion(chosen);
            this.overlayState.runAId = this.currentLogRun?.id || null;
            if (this.overlayState.runBId === this.overlayState.runAId) this.overlayState.runBId = null;
            this.curveRangeCache.clear();
            this._populateLogRunSelector(well.log_runs || [], chosen.id);
            // Auto-populate depth inputs with log run bounds
            const topInput = document.getElementById('depthTop');
            const bottomInput = document.getElementById('depthBottom');
            if (topInput && chosen.start_depth != null) topInput.value = chosen.start_depth;
            if (bottomInput && chosen.stop_depth != null) bottomInput.value = chosen.stop_depth;
            await this._loadCurveData();
            await this._loadFormationTops();
            await this._loadZones();
            this._renderWellHeader(well);
            if (this.currentLogRun) localStorage.setItem('geolog_last_run', logRunId);
            this._refreshPetrophysicsView();
        } catch (e) { console.error('Failed to select log run:', e); }
    }

    _refreshPetrophysicsView() {
        const view = localStorage.getItem('geolog_last_view');
        if (view === 'corescal' && window.CoreScalView) CoreScalView.load();
        else if (view === 'geomechanics' && window.GeomechanicsView) GeomechanicsView.load();
        else if (view === 'imagelog' && window.ImageLogView) ImageLogView.load();
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
            const file = r.filename || 'unknown.log';
            const pts = r.num_points ?? 0;
            const versionLabel = this._formatRunVersion(r.version || r.las_version, file);
            const versionText = versionLabel ? ` • ${versionLabel}` : '';
            return `<option value="${r.id}">Run ${runNo} • ${file} • ${pts} pts${versionText}</option>`;
        }).join('');
        const chosen = selectedId || logRuns[0].id;
        sel.value = String(chosen);
    }

    _formatRunVersion(version, filename = '') {
        const file = String(filename || '').toLowerCase();
        if (file.endsWith('.dlis') || file.includes('.dlis::')) return 'DLIS';
        if (file.endsWith('.lis') || file.includes('.lis::')) return 'LIS';
        if (version == null || version === '') return '';
        const v = String(version).trim();
        if (!v) return '';
        if (v.toUpperCase().includes('DLIS')) return 'DLIS';
        if (v.toUpperCase().includes('LIS')) return 'LIS';
        return v.toUpperCase().startsWith('LAS') ? v.toUpperCase() : `LAS ${v}`;
    }

    _formatLASVersion(version) {
        return this._formatRunVersion(version);
    }

    _normalizeLogRunVersion(logRun) {
        if (!logRun || typeof logRun !== 'object') return logRun;
        const rawVersion = logRun.version || logRun.las_version;
        const normalized = this._formatRunVersion(rawVersion, logRun.filename || '');
        if (!normalized) return logRun;
        return { ...logRun, version: normalized };
    }

    _applyUploadedLASVersion(uploadResult) {
        const versionLabel = this._formatLASVersion(uploadResult?.version);
        if (!versionLabel || !this.currentLogRun) return;
        if (!this.currentLogRun.version) this.currentLogRun.version = versionLabel;
    }

    _curveRangeKey(start, stop, mode = 'full') {
        return `${this.currentLogRun?.id || 0}:${mode}:${start.toFixed(2)}:${stop.toFixed(2)}`;
    }

    _normalizeWindow(start, stop) {
        const s = Number.isFinite(start) ? start : Number(this.currentLogRun?.start_depth || 0);
        const e = Number.isFinite(stop) ? stop : Number(this.currentLogRun?.stop_depth || s + 100);
        const span = Math.max(1, e - s);
        const pad = span * this._viewportPaddingFactor;
        const minDepth = Number(this.currentLogRun?.start_depth ?? s);
        const maxDepth = Number(this.currentLogRun?.stop_depth ?? e);
        return {
            start: Math.max(minDepth, s - pad),
            stop: Math.min(maxDepth, e + pad),
            viewStart: s,
            viewStop: e,
        };
    }

    async _fetchCurveRange(curves, start, stop, { decimated = false } = {}) {
        const mode = decimated ? `decimated-${this.maxPoints}` : 'full';
        const key = this._curveRangeKey(start, stop, mode);
        if (this.curveRangeCache.has(key)) return this.curveRangeCache.get(key);

        const mnemonics = curves.map(c => c.mnemonic);
        let data;
        if (decimated) {
            const dec = await this._api(`/log-runs/${this.currentLogRun.id}/data-decimated?max_points=${this.maxPoints}&start_depth=${encodeURIComponent(start)}&stop_depth=${encodeURIComponent(stop)}`);
            data = { ...(dec?.curves || {}) };
        } else {
            data = await this._api(`/log-runs/${this.currentLogRun.id}/data`, {
                method: 'POST',
                body: JSON.stringify({ curve_mnemonics: mnemonics, start_depth: start, stop_depth: stop }),
            });
        }
        if (data.DEPT && !data.DEPTH) data.DEPTH = data.DEPT;
        this.curveRangeCache.set(key, data);
        return data;
    }

    _applyCurveDataToRenderer(data, curves) {
        const badge = document.getElementById('semanticsBadge');
        if (badge) {
            const sem = data.semantics || {};
            const corrected = sem.depth_source && sem.depth_source !== 'raw';
            const unitChanged = sem.unit_system && sem.unit_system !== 'field';
            if (corrected || unitChanged) {
                badge.style.display = '';
                badge.textContent = corrected ? 'CORRECTED' : 'SI UNITS';
                badge.title = [
                    sem.version || '',
                    sem.depth_source ? 'depth: ' + sem.depth_source : '',
                    sem.unit_system ? 'units: ' + sem.unit_system : '',
                    ...(sem.warnings || []),
                ].filter(Boolean).join(' • ');
            } else {
                badge.style.display = 'none';
            }
        }
        const depth = data.DEPTH || [];
        const curveData = {};
        for (const c of curves) {
            if (data[c.mnemonic]) curveData[c.mnemonic] = data[c.mnemonic];
        }
        this.renderer.setData(depth, curveData, this.formationTops, this.curveConfig);
        this.renderer.setBadHoleIntervals([]);
        const scale = parseInt(document.getElementById('scaleSelect')?.value || '100', 10);
        this.renderer.scale = scale;
        this._renderCurvePanel(curves);
        this._populateCurveSelectors(curves);
        this._populateEditCurveSelector(curves);
        const overlayCurves = [...new Set(curves.map(c => (c.mnemonic || '').toUpperCase()).filter(Boolean))];
        this._populateOverlayControls(overlayCurves);
        if (this.overlayState.enabled) this.applyOverlay();
    }

    _onViewportChanged(start, stop) {
        if (!this.currentLogRun || this._suppressViewportLoad) return;
        clearTimeout(this._curveLoadDebounceTimer);
        this._curveLoadDebounceTimer = setTimeout(() => this._loadCurveData({ viewportStart: start, viewportStop: stop, preserveInputs: true }), 300);
    }

    async _loadCurveData({ viewportStart = null, viewportStop = null, preserveInputs = false } = {}) {
        if (!this.currentLogRun) return;

        try {
            const curves = await this._api(`/log-runs/${this.currentLogRun.id}/curves`);
            const topInput = document.getElementById('depthTop');
            const bottomInput = document.getElementById('depthBottom');
            const inputStart = topInput ? parseFloat(topInput.value) : Number(this.currentLogRun.start_depth);
            const inputStop = bottomInput ? parseFloat(bottomInput.value) : Number(this.currentLogRun.stop_depth);
            const visibleStart = Number.isFinite(viewportStart) ? viewportStart : inputStart;
            const visibleStop = Number.isFinite(viewportStop) ? viewportStop : inputStop;
            const { start, stop, viewStart, viewStop } = this._normalizeWindow(visibleStart, visibleStop);

            if (this.performanceMode) {
                const quick = await this._fetchCurveRange(curves, start, stop, { decimated: true });
                this._applyCurveDataToRenderer(quick, curves);
                const points = quick.DEPTH?.length || quick.DEPT?.length || 0;
                GeoToast.info(`Performance mode ON: ${points} pts`);
                this._fetchCurveRange(curves, start, stop, { decimated: false })
                    .then(full => {
                        this._applyCurveDataToRenderer(full, curves);
                        this._suppressViewportLoad = true;
                        this.renderer.setView(viewStart, viewStop);
                        this._suppressViewportLoad = false;
                    })
                    .catch((e) => console.warn('Background full-resolution load failed:', e?.message || e));
            } else {
                const data = await this._fetchCurveRange(curves, start, stop, { decimated: false });
                this._applyCurveDataToRenderer(data, curves);
            }
            if (this._showLithTrack) await this.toggleLithTrack(true);

            this._suppressViewportLoad = true;
            this.renderer.setView(viewStart, viewStop);
            this._suppressViewportLoad = false;
            if (!preserveInputs) {
                if (topInput) topInput.value = viewStart?.toFixed(1) || '';
                if (bottomInput) bottomInput.value = viewStop?.toFixed(1) || '';
            }
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
            this._updateWorkflowStrip();
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
            this._updateWorkflowStrip();
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



    _pushZoneHistory() {
        if (!this.renderer) return;
        this.zoneUndoStack.push(JSON.parse(JSON.stringify(this.renderer.zones || [])));
        if (this.zoneUndoStack.length > 50) this.zoneUndoStack.shift();
        this.zoneRedoStack = [];
    }

    async undoZone() {
        return this.undo();
    }

    async redoZone() {
        return this.redo();
    }

    // ─── UI Rendering ────────────────────────────────────────
    _renderProjectTree() {
        const container = document.getElementById('projectTree');
        if (!container) return;
        container.innerHTML = this.projects.map(p => `
            <div class="project-group">
                <div class="project-header">
                    <span class="project-name">${escapeHtml(p.name)}</span>
                    <span class="project-meta">${escapeHtml(p.operator || '')} • ${escapeHtml(p.country || '')}</span>
                    <button class="btn-icon-sm" data-action="app.deleteProject" data-args='[${p.id}]' title="Delete">
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
            <div class="well-item" data-id="${w.id}" data-action="app.selectWell" data-args='[${w.id}]'>
                <div class="well-name">${escapeHtml(w.name)}</div>
                <div class="well-meta">${escapeHtml(w.uwi || '—')} • ${w.log_run_count || 0} logs</div>
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

    _populateEditCurveSelector(curves = []) {
        const sel = document.getElementById('editCurveSelect');
        if (!sel) return;
        const mns = [...new Set(curves.map(c => (c.mnemonic || '').toUpperCase()).filter(m => m && m !== 'DEPT' && m !== 'DEPTH'))];
        sel.innerHTML = mns.map(m => `<option value="${m}">${m}</option>`).join('');
        if (!this.curveEditState.mnemonic || !mns.includes(this.curveEditState.mnemonic)) {
            this.curveEditState.mnemonic = mns[0] || null;
        }
        sel.value = this.curveEditState.mnemonic || '';
    }

    toggleOverlayPanel() {
        const panel = document.getElementById('overlayPanel');
        const btn = document.getElementById('overlayToggleBtn');
        if (!panel) return;
        this.overlayState.enabled = !this.overlayState.enabled;
        panel.style.display = this.overlayState.enabled ? 'flex' : 'none';
        if (btn) btn.classList.toggle('active', this.overlayState.enabled);
        if (this.overlayState.enabled) {
            this._populateOverlayControls();
            this.applyOverlay();
        } else {
            this.renderer?.setOverlayData(null);
        }
    }

    onOverlayControlChange(key, value) {
        this.overlayState[key] = value;
        this.applyOverlay();
    }

    clearOverlay() {
        this.overlayState.runBId = null;
        this.overlayState.showDifference = false;
        const runB = document.getElementById('overlayRunB');
        const diff = document.getElementById('overlayShowDiff');
        if (runB) runB.value = '';
        if (diff) diff.checked = false;
        this.renderer?.setOverlayData(null);
        this._renderOverlayLegend();
    }

    _populateOverlayControls(curves = null) {
        const runs = this.currentWell?.log_runs || [];
        if (!runs.length) return;
        if (!this.overlayState.runAId) this.overlayState.runAId = this.currentLogRun?.id || runs[0].id;

        const runASelect = document.getElementById('overlayRunA');
        const runBSelect = document.getElementById('overlayRunB');
        const curveSelect = document.getElementById('overlayCurve');
        const colorInput = document.getElementById('overlayColor');
        const opacityInput = document.getElementById('overlayOpacity');
        const showDiff = document.getElementById('overlayShowDiff');

        if (runASelect) {
            runASelect.innerHTML = runs.map(r => `<option value="${r.id}">Run ${r.run_number || r.id} • ${r.filename || 'log'}</option>`).join('');
            runASelect.value = String(this.overlayState.runAId || '');
        }

        const runBOptions = runs.filter(r => r.id !== this.overlayState.runAId);
        if (!this.overlayState.runBId || !runBOptions.find(r => r.id === this.overlayState.runBId)) {
            this.overlayState.runBId = runBOptions[0]?.id || null;
        }
        if (runBSelect) {
            runBSelect.innerHTML = `<option value="">Select run...</option>` + runBOptions.map(r => `<option value="${r.id}">Run ${r.run_number || r.id} • ${r.filename || 'log'}</option>`).join('');
            runBSelect.value = this.overlayState.runBId ? String(this.overlayState.runBId) : '';
        }

        const mns = curves || [...new Set(Object.keys(this.renderer?.curveData || {}).map(m => m.toUpperCase()).filter(m => m && m !== 'DEPT' && m !== 'DEPTH'))];
        if (curveSelect && mns.length) {
            curveSelect.innerHTML = mns.map(m => `<option value="${m}">${m}</option>`).join('');
            if (!mns.includes(this.overlayState.curve)) this.overlayState.curve = mns.includes('GR') ? 'GR' : mns[0];
            curveSelect.value = this.overlayState.curve;
        }

        if (colorInput) colorInput.value = this.overlayState.color;
        if (opacityInput) opacityInput.value = String(Math.round(this.overlayState.opacity * 100));
        if (showDiff) showDiff.checked = !!this.overlayState.showDifference;
        const lbl = document.getElementById('overlayOpacityLabel');
        if (lbl) lbl.textContent = `${Math.round(this.overlayState.opacity * 100)}%`;
    }

    _lerpAtDepth(depthArr, valueArr, depth) {
        if (!Array.isArray(depthArr) || !Array.isArray(valueArr) || depthArr.length < 2) return null;
        if (depth < depthArr[0] || depth > depthArr[depthArr.length - 1]) return null;
        let lo = 0;
        let hi = depthArr.length - 1;
        while (hi - lo > 1) {
            const mid = (lo + hi) >> 1;
            if (depthArr[mid] <= depth) lo = mid;
            else hi = mid;
        }
        const d0 = depthArr[lo], d1 = depthArr[hi];
        const v0 = valueArr[lo], v1 = valueArr[hi];
        if (!Number.isFinite(v0) || !Number.isFinite(v1) || d1 === d0) return Number.isFinite(v0) ? v0 : null;
        const t = (depth - d0) / (d1 - d0);
        return v0 + (v1 - v0) * t;
    }

    async _fetchOverlayRunCurve(runId, curveMnemonic) {
        const key = `${runId}:${curveMnemonic}`;
        if (this.overlayRunCache.has(key)) return this.overlayRunCache.get(key);
        const run = (this.currentWell?.log_runs || []).find(r => r.id === runId);
        if (!run) return null;
        const data = await this._api(`/log-runs/${runId}/data`, {
            method: 'POST',
            body: JSON.stringify({
                curve_mnemonics: [curveMnemonic],
                start_depth: run.start_depth,
                stop_depth: run.stop_depth,
            }),
        });
        const cached = {
            depth: data.DEPTH || data.DEPT || [],
            curve: data[curveMnemonic] || [],
        };
        this.overlayRunCache.set(key, cached);
        return cached;
    }

    async applyOverlay() {
        if (!this.overlayState.enabled || !this.renderer || !this.currentWell) return;
        this._populateOverlayControls();
        const runAId = Number(this.overlayState.runAId || this.currentLogRun?.id || 0);
        const runBId = Number(this.overlayState.runBId || 0);
        const curve = (this.overlayState.curve || '').toUpperCase();
        if (!runAId || !runBId || !curve) {
            this.renderer.setOverlayData(null);
            this._renderOverlayLegend();
            return;
        }

        try {
            const [a, b] = await Promise.all([
                this._fetchOverlayRunCurve(runAId, curve),
                this._fetchOverlayRunCurve(runBId, curve),
            ]);
            const renderDepth = this.renderer.depthData || [];
            const runAAligned = [];
            const runBAligned = [];
            for (const d of renderDepth) {
                runAAligned.push(this._lerpAtDepth(a?.depth || [], a?.curve || [], d));
                runBAligned.push(this._lerpAtDepth(b?.depth || [], b?.curve || [], d));
            }

            this.renderer.setOverlayData({
                enabled: true,
                mnemonic: curve,
                depth: renderDepth,
                runA: runAAligned,
                runB: runBAligned,
                color: this.overlayState.color,
                opacity: this.overlayState.opacity,
                showDifference: !!this.overlayState.showDifference,
            });
            this._renderOverlayLegend();
        } catch (e) {
            console.error('Failed to apply overlay:', e);
            GeoToast.error('Overlay load failed: ' + (e.message || e));
        }
    }

    _renderOverlayLegend() {
        const el = document.getElementById('overlayLegend');
        if (!el) return;
        const runs = this.currentWell?.log_runs || [];
        const runA = runs.find(r => r.id === Number(this.overlayState.runAId));
        const runB = runs.find(r => r.id === Number(this.overlayState.runBId));
        if (!runA || !runB || !this.overlayState.enabled) {
            el.innerHTML = '';
            return;
        }
        const aName = `Run ${runA.run_number || runA.id}`;
        const bName = `Run ${runB.run_number || runB.id}`;
        el.innerHTML = `<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:14px;height:3px;background:#58a6ff;display:inline-block"></span>${aName}</span> <span style="margin:0 8px">vs</span> <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:14px;height:3px;background:${this.overlayState.color};display:inline-block"></span>${bName}</span>`;
    }

    _activeLogRunForWell(well) {
        if (!well?.log_runs?.length) return null;
        if (this.currentWell?.id === well.id && this.currentLogRun) {
            const same = well.log_runs.find(r => r.id === this.currentLogRun.id);
            if (same) return same;
        }
        return well.log_runs[0];
    }
























    // ─── Actions ─────────────────────────────────────────────

























    // ─── Export ──────────────────────────────────────────────


    // ─── Zone Picking ────────────────────────────────────────








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

    // ─── Pickett Plot ────────────────────────────────────────

    // ─── M-N Plot ───────────────────────────────────────────

    // ─── Petrophysics ────────────────────────────────────────


    // ─── QC / Reliability ───────────────────────────────────

    // ─── Statistics ──────────────────────────────────────────

    async autoZoneFromTops() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        try {
            const result = await this._api(`/wells/${this.currentWell.id}/auto-zone-from-tops`, { method: 'POST' });
            GeoToast.success(`Created ${result.zones_created} zones from formation tops`);
            this._renderZoneStats();
        } catch (e) { GeoToast.error(e.message); }
    }

    async downloadZonationReport() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        try {
            const resp = await fetch(`/api/wells/${this.currentWell.id}/zonation-report`, { headers: this._authHeaders() });
            if (!resp.ok) throw new Error(await resp.text());
            const blob = await resp.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${this.currentWell.name || 'well'}_zonation_report.csv`;
            a.click();
            GeoToast.success('Zonation report downloaded');
        } catch (e) { GeoToast.error(e.message); }
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

    // ─── Saturation Model Selector ───────────────────────────
    _onSatModelChange() {
        const model = document.getElementById('satModel')?.value || 'archie';
        // Show/hide n parameter for non-Archie models
        const nRow = document.getElementById('archN')?.closest('.form-row');
        if (nRow) nRow.style.display = model === 'archie' ? '' : 'none';
    }

    // ─── Workflow Templates ───────────────────────────────────
    async loadWorkflowTemplates() {
        try {
            const res = await this._api('/templates');
            this.workflowTemplates = Array.isArray(res?.templates) ? res.templates : [];
            this.renderTemplateCards();
        } catch (e) {
            this.workflowTemplates = [];
            this.renderTemplateCards();
        }
    }

    renderTemplateCards() {
        const host = document.getElementById('templateCards');
        if (!host) return;
        if (!this.workflowTemplates.length) {
            host.innerHTML = '<div style="color:#8b949e;font-size:12px">No templates available.</div>';
            return;
        }
        host.innerHTML = this.workflowTemplates.map((t, idx) => {
            const p = t.params || {};
            const c = t.recommended_cutoffs || {};
            return `<div style="border:1px solid #30363d;border-radius:8px;padding:8px;background:#0d1117">
                <div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
                    <strong>${escapeHtml(t.name || 'Template')}</strong>
                    <button class="btn-sm" data-action="app.previewTemplate" data-args='[${idx}]'>Preview</button>
                </div>
                <div style="font-size:12px;color:#8b949e;margin:4px 0">${escapeHtml(t.description || '')}</div>
                <div style="font-size:12px;color:#c9d1d9">a=${p.a}, m=${p.m}, n=${p.n}, Vcl≤${c.vsh_cutoff}, PHIE≥${c.phie_cutoff}, Sw≤${c.sw_cutoff}</div>
                <div style="margin-top:6px"><button class="btn-primary" data-template-index="${idx}">Apply Template</button></div>
            </div>`;
        }).join('');
    }

    previewTemplate(index) {
        const t = this.workflowTemplates?.[index];
        const el = document.getElementById('templatePreview');
        if (!el || !t) return;
        const p = t.params || {};
        const c = t.recommended_cutoffs || {};
        el.innerHTML = `Preview: <strong>${escapeHtml(t.name)}</strong> → model=${escapeHtml(p.saturation_model || 'archie')}, a=${p.a}, m=${p.m}, n=${p.n}, Rw=${t.suggested_rw ?? p.rw}, Vcl≤${c.vsh_cutoff}, PHIE≥${c.phie_cutoff}, Sw≤${c.sw_cutoff}, GR range ${c.gr_min}-${c.gr_max}.`;
    }

    async applyWorkflowTemplate(templateName) {
        if (!this.currentWell) return GeoToast.warn('Select a well first');
        const yes = window.confirm(`Apply template "${templateName}" to this well? This will overwrite current petrophysical parameters.`);
        if (!yes) return;
        try {
            const result = await this._api(`/wells/${this.currentWell.id}/apply-template`, {
                method: 'POST',
                body: JSON.stringify({ template_name: templateName }),
            });
            await this.loadPetroParams();
            await this._renderPetrophysics();
            await this.loadTemplateLockStatus();
            GeoToast.success(`Applied: ${result?.applied_template || templateName}`);
        } catch (e) {
            GeoToast.error('Template apply failed: ' + (e.message || e));
        }
    }

    applyPetroTemplate(templateName) {
        // Backward compatibility for old UI callbacks
        return this.applyWorkflowTemplate(templateName);
    }

    // ─── Save/Load Petro Params ──────────────────────────────
    async savePetroParams() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const getVal = (id) => parseFloat(document.getElementById(id)?.value || '0');
        const model = document.getElementById('satModel')?.value || 'archie';
        try {
            const resp = await this._api(`/wells/${this.currentWell.id}/petro-params`, {
                method: 'POST',
                body: JSON.stringify({
                    saturation_model: model,
                    a: getVal('archA'), m: getVal('archM'), n: getVal('archN'), rw: getVal('archRw'),
                    vsh_cutoff: getVal('cutVsh'), phie_cutoff: getVal('cutPhie'), sw_cutoff: getVal('cutSw'),
                    template: 'custom',
                }),
            });
            GeoToast.success(`Petro params saved (sig ${String(resp?.signature || '').slice(0, 12)})`);
            await this.loadTemplateLockStatus();
        } catch (e) {
            GeoToast.error('Save params failed: ' + (e.message || e));
        }
    }

    async loadTemplateLockStatus() {
        const el = document.getElementById('templateLockStatus');
        if (!el || !this.currentWell) return;
        try {
            const st = await this._api(`/wells/${this.currentWell.id}/template-lock-status`);
            this.templateLockStatus = st || null;
            if (st?.locked) {
                const ok = st.signature_matches === true ? 'match' : (st.signature_matches === false ? 'MISMATCH' : 'n/a');
                el.innerHTML = `Template lock: <strong style="color:#f85149">LOCKED</strong> by ${escapeHtml(st.locked_by || 'n/a')} | template=${escapeHtml(st.signed_template || 'custom')} | sig=${escapeHtml(String(st.signature || '').slice(0,12))} | state=${ok}`;
            } else {
                el.innerHTML = `Template lock: <strong style="color:#3fb950">UNLOCKED</strong> | current sig=${String(st?.current_signature || '').slice(0,12)}`;
            }
        } catch (e) {
            el.innerHTML = 'Template lock: unavailable';
        }
    }

    async lockTemplateSignature() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const actor = window.prompt('Lock actor (name/initial)?', 'interpreter') || 'interpreter';
        const reason = window.prompt('Lock reason?', 'QA approved template') || 'QA approved template';
        try {
            const out = await this._api(`/wells/${this.currentWell.id}/template-lock`, {
                method: 'POST',
                headers: { 'X-User-Role': 'admin' },
                body: JSON.stringify({ actor, reason }),
            });
            GeoToast.success(`Template locked: ${String(out?.signature || '').slice(0,12)}`);
            await this.loadTemplateLockStatus();
        } catch (e) {
            GeoToast.error('Lock failed: ' + (e.message || e));
        }
    }

    async unlockTemplateSignature() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const actor = window.prompt('Unlock actor?', 'admin') || 'admin';
        try {
            await this._api(`/wells/${this.currentWell.id}/template-unlock`, {
                method: 'POST',
                headers: { 'X-User-Role': 'admin' },
                body: JSON.stringify({ actor }),
            });
            GeoToast.success('Template unlocked');
            await this.loadTemplateLockStatus();
        } catch (e) {
            GeoToast.error('Unlock failed: ' + (e.message || e));
        }
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
            await this.loadTemplateLockStatus();
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

    // ─── Enhanced Statistics with Histogram ──────────────────


    // ─── Sensitivity Analysis ────────────────────────────────



    // ─── Cross Section (repurposed Comparison view) ─────────
    async loadWellComparison() {
        if (!this.projects || !this.projects.length) return GeoToast.warn('No project loaded');
        const pid = this.projects[0].id;
        const curve = document.getElementById('crossSectionCurve')?.value || 'GR';
        const vScale = Math.max(0.2, parseFloat(document.getElementById('crossSectionVScale')?.value || '1'));
        const showTops = !!document.getElementById('crossSectionShowTops')?.checked;
        const showCorr = !!document.getElementById('crossSectionShowCorr')?.checked;
        const selectedIds = (this.wells || []).map(w => w.id).join(',');
        GeoLoading.show('Loading cross section...');
        try {
            const data = await this._api(`/projects/${pid}/cross-section?curve=${encodeURIComponent(curve)}&well_ids=${encodeURIComponent(selectedIds)}`);
            const canvas = document.getElementById('crossSectionCanvas');
            const panel = document.getElementById('comparisonContent');
            if (!canvas || !panel) return;
            const wells = data.wells || [];
            if (!wells.length) {
                const ctx = canvas.getContext('2d');
                canvas.width = panel.clientWidth || 900; canvas.height = 500;
                ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#8b949e'; ctx.textAlign = 'center'; ctx.font = '14px DM Sans';
                ctx.fillText('No cross-section data available.', canvas.width / 2, canvas.height / 2);
                return;
            }

            // Global extents
            let dMin = Infinity, dMax = -Infinity, vMin = Infinity, vMax = -Infinity;
            for (const w of wells) {
                if (w.depth?.length) {
                    dMin = Math.min(dMin, ...w.depth);
                    dMax = Math.max(dMax, ...w.depth);
                }
                const valid = (w.values || []).filter(v => v !== null && !isNaN(v));
                if (valid.length) {
                    vMin = Math.min(vMin, ...valid);
                    vMax = Math.max(vMax, ...valid);
                }
            }
            if (!isFinite(dMin) || !isFinite(dMax)) return;
            if (!isFinite(vMin) || !isFinite(vMax) || Math.abs(vMax - vMin) < 1e-9) { vMin = 0; vMax = 1; }

            const margin = { top: 52, right: 40, bottom: 26, left: 72 };
            const plotW = Math.max(700, (panel.clientWidth || 1000) - margin.left - margin.right);
            const plotH = Math.max(560, (dMax - dMin) * 0.08 * vScale);
            canvas.width = margin.left + plotW + margin.right;
            canvas.height = margin.top + plotH + margin.bottom;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, canvas.width, canvas.height);

            const xs = wells.map(w => Number(w.x || 0));
            const xMin = Math.min(...xs), xMax = Math.max(...xs);
            const sx = x => margin.left + ((x - xMin) / ((xMax - xMin) || 1)) * plotW;
            const sy = d => margin.top + ((d - dMin) / ((dMax - dMin) || 1)) * plotH;
            const trackW = Math.max(28, Math.min(80, plotW / Math.max(2, wells.length * 3)));

            this._crossSectionPick = [];
            this._crossSectionHover = [];

            // Correlation lines first
            if (showCorr) {
                const forms = data.formation_names || [];
                for (const fn of forms) {
                    const pts = [];
                    for (const w of wells) {
                        const top = (w.tops || []).find(t => t.name === fn);
                        if (!top) continue;
                        pts.push({ x: sx(w.x), y: sy(top.depth), color: top.color || '#6e7681' });
                    }
                    if (pts.length >= 2) {
                        ctx.strokeStyle = '#ffffff33';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([5, 4]);
                        ctx.beginPath();
                        ctx.moveTo(pts[0].x, pts[0].y);
                        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
                        ctx.stroke();
                        ctx.setLineDash([]);
                    }
                }
            }

            // Wells/tracks
            for (const w of wells) {
                const cx = sx(w.x);
                const left = cx - trackW / 2;
                const right = cx + trackW / 2;
                const topY = margin.top;
                const baseY = margin.top + plotH;

                ctx.fillStyle = '#161b22';
                ctx.fillRect(left, topY, trackW, plotH);
                ctx.strokeStyle = (this.currentWell?.id === w.well_id) ? '#58a6ff' : '#30363d';
                ctx.lineWidth = (this.currentWell?.id === w.well_id) ? 2 : 1;
                ctx.strokeRect(left, topY, trackW, plotH);
                this._crossSectionPick.push({ wellId: w.well_id, x1: left, x2: right, y1: topY, y2: baseY });

                // Filled curve
                const vals = w.values || [];
                const dep = w.depth || [];
                ctx.beginPath();
                let started = false;
                for (let i = 0; i < dep.length; i++) {
                    const v = vals[i];
                    if (v === null || isNaN(v)) continue;
                    const y = sy(dep[i]);
                    const frac = (v - vMin) / ((vMax - vMin) || 1);
                    const x = left + Math.max(0, Math.min(1, frac)) * trackW;
                    if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
                    this._crossSectionHover.push({ x, y, depth: dep[i], value: v, wellName: w.name, curve });
                }
                if (started) {
                    ctx.lineTo(left, sy(dep[dep.length - 1] || dMax));
                    ctx.lineTo(left, sy(dep.find(d => Number.isFinite(d)) || dMin));
                    ctx.closePath();
                    ctx.fillStyle = '#58a6ff33';
                    ctx.fill();
                    ctx.strokeStyle = '#58a6ff';
                    ctx.lineWidth = 1.1;
                    ctx.stroke();
                }

                if (showTops) {
                    for (const t of (w.tops || [])) {
                        const y = sy(t.depth);
                        if (y < topY || y > baseY) continue;
                        const c = t.color || '#888888';
                        ctx.strokeStyle = c;
                        ctx.lineWidth = 1.4;
                        ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
                        if (t.lithology) {
                            ctx.fillStyle = c + '33';
                            ctx.fillRect(left, y - 2, trackW, 4);
                        }
                    }
                }

                ctx.fillStyle = '#c9d1d9';
                ctx.font = 'bold 11px DM Sans';
                ctx.textAlign = 'center';
                ctx.fillText(w.name, cx, margin.top - 24);
            }

            // Depth axis
            ctx.strokeStyle = '#6e7681'; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(margin.left - 8, margin.top); ctx.lineTo(margin.left - 8, margin.top + plotH); ctx.stroke();
            const tick = Math.max(10, Math.ceil(((dMax - dMin) / 12) / 10) * 10);
            ctx.font = '10px IBM Plex Mono'; ctx.textAlign = 'right'; ctx.fillStyle = '#8b949e';
            for (let d = Math.ceil(dMin / tick) * tick; d <= dMax; d += tick) {
                const y = sy(d);
                ctx.fillText(d.toFixed(0), margin.left - 12, y + 3);
                ctx.strokeStyle = '#21262d'; ctx.lineWidth = 0.7;
                ctx.beginPath(); ctx.moveTo(margin.left, y); ctx.lineTo(margin.left + plotW, y); ctx.stroke();
            }

            this._bindCrossSectionInteractions(canvas, panel, wells);
        } catch (e) {
            GeoToast.error('Cross section failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    }

    _bindCrossSectionInteractions(canvas, panel, wells) {
        const tooltip = document.getElementById('crossSectionTooltip');
        if (!canvas || !panel || !tooltip) return;
        canvas.onmousemove = (e) => {
            const rect = canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;
            let nearest = null; let best = 14;
            for (const p of (this._crossSectionHover || [])) {
                const d = Math.hypot(mx - p.x, my - p.y);
                if (d < best) { best = d; nearest = p; }
            }
            if (!nearest) { tooltip.style.display = 'none'; return; }
            tooltip.style.display = 'block';
            tooltip.style.left = `${mx + 12}px`;
            tooltip.style.top = `${my + 12}px`;
            tooltip.innerHTML = `<strong>${escapeHtml(nearest.wellName)}</strong><br>Depth: ${Number(nearest.depth).toFixed(1)}<br>${escapeHtml(nearest.curve)}: ${Number(nearest.value).toFixed(3)}`;
        };
        canvas.onmouseleave = () => { tooltip.style.display = 'none'; };
        canvas.onclick = async (e) => {
            const rect = canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;
            const hit = (this._crossSectionPick || []).find(w => mx >= w.x1 && mx <= w.x2 && my >= w.y1 && my <= w.y2);
            if (hit) {
                await this.selectWell(hit.wellId);
                this.loadWellComparison();
            }
        };
    }

    exportComparisonCSV() {
        GeoToast.info('Cross section view does not export table CSV.');
    }




    // ─── Tools Panel Init ────────────────────────────────────
    async _initToolsPanel() {
        if (!this.currentWell) return;
        await this._populateToolRunSelectors();
        await this.loadAnnotations();
        await this.loadDST();
        await this.loadRFT();
        await this.loadCompletion();
        this._initRFTCSVUpload();
        const compToggle = document.getElementById('completionTrackToggle');
        if (compToggle) compToggle.checked = this.showCompletionTrack;
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
            const lqcCurveSel = document.getElementById('lqcCurveSelect');
            if (lqcCurveSel) {
                const curves = Object.keys(this.renderer?.curveData || {}).filter(c => c && c !== 'DEPT' && c !== 'DEPTH');
                lqcCurveSel.innerHTML = curves.map(c => `<option value="${c}">${c}</option>`).join('');
                if (curves.includes('RT')) lqcCurveSel.value = 'RT';
                else if (curves.includes('GR')) lqcCurveSel.value = 'GR';
            }
        } catch { /* no runs */ }
    }




    // ─── Bulk LAS Upload ─────────────────────────────────────
    _initBulkUpload() {
        const cardInput = document.getElementById('bulkFileInput');
        if (cardInput && !cardInput._bound) {
            cardInput._bound = true;
            cardInput.addEventListener('change', async () => {
                const files = cardInput.files;
                const status = document.getElementById('bulkUploadStatus');
                if (!files || !files.length) return;
                if (status) status.textContent = `${files.length} file(s) selected`;
                this.openBulkImportWizard();
                await this._startBulkImport(files);
                cardInput.value = '';
            });
        }

        const wizInput = document.getElementById('bulkImportFileInput');
        if (wizInput && !wizInput._bound) {
            wizInput._bound = true;
            wizInput.addEventListener('change', async () => {
                const files = wizInput.files;
                if (!files || !files.length) return;
                await this._startBulkImport(files);
                wizInput.value = '';
            });
        }

        const dropZone = document.getElementById('bulkDropZone');
        if (dropZone && !dropZone._bound) {
            dropZone._bound = true;
            dropZone.addEventListener('click', () => wizInput?.click());
            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.style.borderColor = '#58a6ff';
            });
            dropZone.addEventListener('dragleave', () => {
                dropZone.style.borderColor = '#30363d';
            });
            dropZone.addEventListener('drop', async (e) => {
                e.preventDefault();
                dropZone.style.borderColor = '#30363d';
                const files = e.dataTransfer?.files;
                if (!files || !files.length) return;
                await this._startBulkImport(files);
            });
        }
    }

    // ─── Depth Shift ─────────────────────────────────────────



    // ─── Curve Splice ────────────────────────────────────────

    // ─── Annotations ─────────────────────────────────────────





















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

    toggleEditMode() {
        this.curveEditState.enabled = !this.curveEditState.enabled;
        const btn = document.getElementById('editModeToggle');
        if (btn) btn.classList.toggle('active', this.curveEditState.enabled);
        if (!this.curveEditState.enabled) {
            this.hideEditValueInput();
        }
        this.resetCurveEditSession();
        this.refreshCurveEditUI();
    }

    setEditCurve(mnemonic) {
        this.curveEditState.mnemonic = mnemonic || null;
        this.resetCurveEditSession();
        this.refreshCurveEditUI();
    }

    resetCurveEditSession() {
        this.curveEditState.originals = {};
        this.curveEditState.selected = [];
        this.curveEditState.edits = {};
        this.curveEditState.history = [];
        this.curveEditState.nextId = 1;
        this.refreshCurveEditOverlay();
        this.renderCurveEditHistory();
    }

    onCurveEditCanvasClick(e) {
        if (!this.renderer || !this.curveEditState.enabled) return;
        const canvas = document.getElementById('logCanvas');
        const rect = canvas.getBoundingClientRect();
        const p = this.renderer.getNearestCurvePoint(e.clientX - rect.left, e.clientY - rect.top, this.curveEditState.mnemonic);
        if (!p) return;
        if (!this.curveEditState.mnemonic) {
            this.curveEditState.mnemonic = p.mnemonic;
            const sel = document.getElementById('editCurveSelect');
            if (sel) sel.value = p.mnemonic;
        }
        if (p.mnemonic !== this.curveEditState.mnemonic) return;

        const key = String(p.index);
        if (!e.ctrlKey) this.curveEditState.selected = [];
        if (!this.curveEditState.selected.includes(key)) this.curveEditState.selected.push(key);
        this.showEditValueInputNear(p);
        this.refreshCurveEditOverlay();
        this.refreshCurveEditUI();
    }

    showEditValueInputNear(point) {
        const box = document.getElementById('editValuePopover');
        const input = document.getElementById('editValueInput');
        const canvas = document.getElementById('logCanvas');
        if (!box || !input || !canvas) return;
        const rect = canvas.getBoundingClientRect();
        box.style.display = 'block';
        box.style.left = `${Math.round(rect.left + point.x + 10)}px`;
        box.style.top = `${Math.round(rect.top + point.y - 14)}px`;
        input.value = Number.isFinite(point.value) ? Number(point.value).toFixed(4) : '';
        input.focus();
        input.select();
    }

    hideEditValueInput() { const box = document.getElementById('editValuePopover'); if (box) box.style.display = 'none'; }

    applyEditValueInput() {
        const input = document.getElementById('editValueInput');
        if (!input || !this.curveEditState.selected.length) return;
        const raw = input.value.trim();
        const val = raw === '' ? null : Number(raw);
        if (raw !== '' && !Number.isFinite(val)) return GeoToast.warn('Enter a numeric value or blank to null');
        this.applyValueToSelected(val);
    }

    applyValueToSelected(newValue) {
        const mnem = this.curveEditState.mnemonic;
        const depth = this.renderer?.depthData || [];
        const curve = this.renderer?.curveData?.[mnem] || [];
        for (const key of this.curveEditState.selected) {
            const idx = parseInt(key, 10);
            if (!Number.isFinite(idx) || idx < 0 || idx >= curve.length) continue;
            if (!(key in this.curveEditState.originals)) this.curveEditState.originals[key] = curve[idx];
            const oldValue = this.curveEditState.edits[key]?.oldValue ?? this.curveEditState.originals[key];
            this.curveEditState.edits[key] = { index: idx, depth: depth[idx], oldValue, newValue };
            this.curveEditState.history.push({ id: this.curveEditState.nextId++, index: idx, depth: depth[idx], oldValue, newValue });
            curve[idx] = newValue;
        }
        this.renderer.curveData[mnem] = curve;
        this.hideEditValueInput();
        this.refreshCurveEditOverlay();
        this.renderCurveEditHistory();
        this.refreshCurveEditUI();
        this.renderer.render();
    }

    deleteSelectedEditPoints() { this.applyValueToSelected(null); }

    revertCurveEditHistoryItem(id) {
        const item = this.curveEditState.history.find(h => h.id === id);
        if (!item) return;
        this.curveEditState.selected = [String(item.index)];
        this.applyValueToSelected(item.oldValue ?? null);
    }

    renderCurveEditHistory() {
        const el = document.getElementById('editHistoryList');
        if (!el) return;
        if (!this.curveEditState.history.length) {
            el.innerHTML = '<div style="color:#8b949e">No edits yet.</div>';
            return;
        }
        el.innerHTML = this.curveEditState.history.slice().reverse().map(h => {
            const ov = h.oldValue == null || Number.isNaN(h.oldValue) ? 'null' : Number(h.oldValue).toFixed(4);
            const nv = h.newValue == null || Number.isNaN(h.newValue) ? 'null' : Number(h.newValue).toFixed(4);
            return `<div class="edit-history-item"><span>${Number(h.depth).toFixed(2)}: ${ov} → ${nv}</span><button class="btn-sm" data-action="app.revertCurveEditHistoryItem" data-args='[${h.id}]'>Revert</button></div>`;
        }).join('');
    }

    refreshCurveEditOverlay() {
        if (!this.renderer) return;
        const m = this.curveEditState.mnemonic;
        const selected = [];
        const edited = [];
        const ghosts = [];
        for (const key of Object.keys(this.curveEditState.edits)) {
            const e = this.curveEditState.edits[key];
            const pNew = this.renderer.getCurvePointAtIndex(m, e.index);
            if (pNew) edited.push(pNew);
            const oldVal = this.curveEditState.originals[key];
            if (oldVal != null && Number.isFinite(oldVal)) {
                const pOld = this.renderer.getCurvePointAtIndex(m, e.index, oldVal);
                if (pOld) ghosts.push(pOld);
            }
        }
        for (const key of this.curveEditState.selected) {
            const idx = parseInt(key, 10);
            const p = this.renderer.getCurvePointAtIndex(m, idx);
            if (p) selected.push(p);
        }
        this.renderer.setEditOverlay({ enabled: this.curveEditState.enabled, mnemonic: m, selected, edited, ghosts });
    }

    refreshCurveEditUI() {
        const dirty = Object.keys(this.curveEditState.edits).length > 0;
        const dirtyEl = document.getElementById('editDirtyIndicator');
        if (dirtyEl) dirtyEl.textContent = dirty ? '● Unsaved edits' : 'No unsaved edits';
        const saveBtn = document.getElementById('editSaveBtn');
        const cancelBtn = document.getElementById('editCancelBtn');
        if (saveBtn) saveBtn.disabled = !dirty;
        if (cancelBtn) cancelBtn.disabled = !dirty;
    }

    async saveCurveEdits() {
        if (!this.currentLogRun || !this.curveEditState.mnemonic) return;
        const edits = Object.values(this.curveEditState.edits).map(e => ({ depth: e.depth, new_value: e.newValue }));
        if (!edits.length) return;
        GeoLoading.show('Saving curve edits...');
        try {
            const res = await this._api('/log-runs/' + this.currentLogRun.id + '/curve-edit', {
                method: 'POST', body: JSON.stringify({ mnemonic: this.curveEditState.mnemonic, edits }),
            });
            GeoToast.success('Saved ' + (res.applied_count || edits.length) + ' edits');
            await this._loadCurveData();
            this.resetCurveEditSession();
            this.refreshCurveEditUI();
        } catch (e) { GeoToast.error('Save edits failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    }

    async cancelCurveEdits() {
        await this._loadCurveData();
        this.resetCurveEditSession();
        this.hideEditValueInput();
        this.refreshCurveEditUI();
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
                '<button class="btn-sm" data-action="app._saveAutoPicks" style="margin-top:8px">Save All Picks</button>';

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
                const resp = await fetch('/api/wells/' + this.currentWell.id + '/upload-csv', {
                    method: 'POST',
                    body: formData,
                    headers: this._authHeaders(),
                });
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


    // ─── Sprint 21: Probability Plot ──────────────────────────────


    // ─── Sprint 21: Moveable Oil ──────────────────────────────────


    // ─── Sprint 21: Dip Plot ──────────────────────────────────────


    // ─── Sprint 22: Buckles Plot ─────────────────────────────────


    // ─── Sprint 22: Hingle Plot ──────────────────────────────────


    // ─── Sprint 22: Curve Calculator ─────────────────────────────

    // ─── Sprint 23: Data Table ────────────────────────────────────



    // ─── Sprint 23: Tops Management ──────────────────────────────





    // ─── Sprint 24: Well Location Map ─────────────────────────────

    // ─── Sprint 24: Project Summary Dashboard ─────────────────────

    // ─── Sprint 23: Formation Matrix ─────────────────────────────

    // ─── Sprint 23: Batch Petrophysics ────────────────────────────




    openShortcutHelp() {
        const modal = document.getElementById('shortcutModal');
        if (modal) modal.style.display = 'flex';
    }

    closeShortcutHelp(event = null) {
        if (event && event.target && event.target.id !== 'shortcutModal') return;
        const modal = document.getElementById('shortcutModal');
        if (modal) modal.style.display = 'none';
    }

    _toggleDetailsPanels() {
        const panels = document.getElementById('bottomPanels');
        if (!panels) return;
        panels.style.display = (panels.style.display === 'none') ? 'grid' : 'none';
    }

    _toggleAdvancedControls() {
        const controls = document.getElementById('advancedControls');
        const btn = document.getElementById('advancedToggleBtn');
        if (!controls || !btn) return;
        controls.classList.toggle('open');
        btn.classList.toggle('active');
    }

    _toggleFullscreenViewer() {
        const target = document.getElementById('viewerPanel') || document.documentElement;
        if (!document.fullscreenElement) {
            target.requestFullscreen?.().catch(() => {});
        } else {
            document.exitFullscreen?.().catch(() => {});
        }
    }

    _jumpToWellBoundary(toBottom = false) {
        if (!this.renderer?.depthData?.length) return;
        const dataStart = this.renderer.depthData[0];
        const dataEnd = this.renderer.depthData[this.renderer.depthData.length - 1];
        const range = this.renderer.viewStop - this.renderer.viewStart;
        if (toBottom) this.renderer.setView(Math.max(dataStart, dataEnd - range), dataEnd);
        else this.renderer.setView(dataStart, Math.min(dataEnd, dataStart + range));
    }

    async _saveCurrentAnnotations() {
        if (this.currentView === 'correlation') {
            await this._saveCorrelationMarkers();
            GeoToast.success('Correlation markers saved');
            return;
        }
        await this._saveZones();
        GeoToast.success('Picks/annotations saved');
    }


    // ─── Sprint 26: Status Bar ──────────────────────────────────
    _updateStatusBar(view) {
        const el = document.getElementById('statusView');
        if (el) {
            const names = { viewer: 'Log Viewer', crossplot: 'Cross Plot', pickett: 'Pickett', mnplot: 'M-N Plot',
                petrophysics: 'Petrophysics', qc: 'QC', statistics: 'Statistics', sensitivity: 'Sensitivity',
                comparison: 'Cross Section', correlation: 'Correlation', striplog: 'Strip Log', facies: 'Facies',
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
        cm.innerHTML = items.map((item, index) => {
            if (item.separator) return '<div class="context-menu-sep"></div>';
            return `<div class="context-menu-item ${item.danger ? 'danger' : ''}" data-context-index="${index}">
                <i data-lucide="${item.icon || 'circle'}"></i> ${escapeHtml(item.label)}
            </div>`;
        }).join('');
        cm.querySelectorAll('[data-context-index]').forEach(el => {
            el.addEventListener('click', () => {
                const item = items[Number(el.dataset.contextIndex)];
                cm.style.display = 'none';
                item?.run?.();
            });
        });
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
            { label: 'Log Viewer', icon: 'activity', run: () => this.switchView('viewer'), shortcut: '1' },
            { label: 'Cross Plot', icon: 'scatter-chart', run: () => this.switchView('crossplot'), shortcut: '2' },
            { label: 'Pickett Plot', icon: 'chart-no-axes-combined', run: () => this.switchView('pickett'), shortcut: '3' },
            { label: 'Petrophysics', icon: 'calculator', run: () => this.switchView('petrophysics'), shortcut: '4' },
            { label: 'QC', icon: 'shield-check', run: () => this.switchView('qc'), shortcut: '5' },
            { label: 'Statistics', icon: 'bar-chart-3', run: () => this.switchView('statistics'), shortcut: '6' },
            { label: 'Correlation', icon: 'split-square-horizontal', run: () => this.switchView('correlation'), shortcut: '7' },
            { label: 'Sensitivity', icon: 'git-compare', run: () => this.switchView('sensitivity') },
            { label: 'Facies', icon: 'gem', run: () => this.switchView('facies'), shortcut: '9' },
            { label: 'Data Table', icon: 'table', run: () => this.switchView('datatable') },
            { label: 'Map', icon: 'map-pin', run: () => this.switchView('map') },
            { label: 'Dashboard', icon: 'layout-dashboard', run: () => this.switchView('dashboard') },
            { label: 'Matrix Plot', icon: 'grid-3x3', run: () => this.switchView('matrix') },
            { label: 'Audit Trail', icon: 'file-text', run: () => this.switchView('audit') },
            { label: 'Upload LAS', icon: 'upload', run: () => this.uploadLAS() },
            { label: 'Upload DLIS', icon: 'file-up', run: () => this.uploadDLIS() },
            { label: 'Upload LIS', icon: 'file-up', run: () => this.uploadLIS() },
            { label: 'Export Report', icon: 'file-down', run: () => this.exportReport() },
            { label: 'Export PNG', icon: 'image', run: () => this._exportPNG() },
            { label: 'Keyboard Shortcuts', icon: 'keyboard', run: () => this.openShortcutHelp(), shortcut: '?' },
        ];
        const q = query.toLowerCase();
        const filtered = q ? commands.filter(c => c.label.toLowerCase().includes(q)) : commands;
        const container = document.getElementById('cmdPaletteResults');
        container.innerHTML = filtered.map((c, index) =>
            `<div class="cmd-palette-item" data-command-index="${index}">
                <i data-lucide="${escapeHtml(c.icon)}"></i> ${escapeHtml(c.label)}
                ${c.shortcut ? `<span class="shortcut">${escapeHtml(c.shortcut)}</span>` : ''}
            </div>`
        ).join('');
        container.querySelectorAll('[data-command-index]').forEach(el => {
            el.addEventListener('click', () => {
                const command = filtered[Number(el.dataset.commandIndex)];
                this.closeCmdPalette();
                command?.run?.();
            });
        });
        if (typeof lucide !== 'undefined') lucide.createIcons({ attrs: { 'stroke-width': 1.5 } });
    }

    // ─── Sprint 26: Audit Trail ─────────────────────────────────


    // ─── Sprint 26: Cross-Plot Matrix ───────────────────────────


    // ─── Sprint 26: Well Report Export ──────────────────────────


    // ─── Sprint 26: Context Menu for Wells ──────────────────────
    _bindContextMenu() {
        // Right-click on well items in sidebar
        document.addEventListener('contextmenu', (e) => {
            const wellItem = e.target.closest('.well-item');
            if (wellItem) {
                e.preventDefault();
                const wid = parseInt(wellItem.dataset.id);
                this.showContextMenu(e.clientX, e.clientY, [
                    { label: 'Select Well', icon: 'check', run: () => this.selectWell(wid) },
                    { label: 'Edit Well', icon: 'pencil', run: () => this.editWell(wid) },
                    { separator: true },
                    { label: 'Upload LAS', icon: 'upload', run: () => this.uploadLASForWell(wid) },
                    { label: 'Upload DLIS', icon: 'file-up', run: () => this.uploadDLISForWell(wid) },
                    { label: 'Upload LIS', icon: 'file-up', run: () => this.uploadLISForWell(wid) },
                    { label: 'Export Report', icon: 'file-down', run: () => { this.currentWell = wid; this.exportReport(); } },
                    { label: 'Export Package', icon: 'package', run: () => this._exportPackage(wid) },
                    { separator: true },
                    { label: 'Delete Well', icon: 'trash-2', run: () => this.deleteWell(wid), danger: true },
                ]);
            }
        });
    }

    async _exportPackage(wid) {
        try {
            const resp = await fetch(`/api/wells/${wid}/export-package`, { headers: this._authHeaders() });
            const data = await resp.json();
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `well_${wid}_package.json`;
            a.click();
            GeoToast.success('Package exported');
        } catch { GeoToast.error('Export failed'); }
    }




    async editWell(wid) {
        await this.selectWell(wid);
        this.editCurrentWell();
    }


    // ─── Sprint 27: Tornado Chart ───────────────────────────────


    // ─── Sprint 27: Vcl Models ──────────────────────────────────



    // ─── Sprint 27: Core Calibration ────────────────────────────



    // ─── Sprint 27: QC Auto-Fix ─────────────────────────────────


    _publishDepthSync(depth, source) {
        if (!this.depthSync?.enabled) return;
        if (!Number.isFinite(depth) || depth <= 0) return;
        this.depthSync.activeDepth = depth;
        this.depthSync.source = source || 'unknown';
        if (source !== 'seismic') this._drawSeismicDepthMarker(depth);
        if (source !== 'imagelog') this._drawImageDepthMarker(depth);
        if (source !== 'viewer') this._drawViewerDepthMarker(depth);
    }

    _drawViewerDepthMarker(depth) {
        if (!this.renderer || !Number.isFinite(depth)) return;
        this.renderer.hoverDepth = depth;
        this.renderer.requestRender();
    }

    _drawSeismicDepthMarker(depth) {
        const s = this._seismicSyncCtx;
        if (!s || !s.ctx) return;
        const { ctx, W, H, pad, ph, dMin, dMax, baseImage } = s;
        if (baseImage) ctx.putImageData(baseImage, 0, 0);
        const y = pad.top + ((depth - dMin) / ((dMax - dMin) || 1)) * ph;
        if (y < pad.top || y > pad.top + ph) return;
        ctx.save();
        ctx.strokeStyle = '#ff4d4f';
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(W - pad.right, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#ff4d4f';
        ctx.font = '11px JetBrains Mono';
        ctx.textAlign = 'left';
        ctx.fillText(`${depth.toFixed(1)} ft`, pad.left + 6, y - 6);
        ctx.restore();
    }

    _drawImageDepthMarker(depth) {
        const s = this._imageSyncCtx;
        if (!s || !s.ctx) return;
        const { ctx, startX, drawTop, cellH, nDepths, depthArr, totalW, baseImage } = s;
        if (baseImage) ctx.putImageData(baseImage, 0, 0);
        if (!depthArr?.length || nDepths <= 1) return;
        const dMin = depthArr[0], dMax = depthArr[depthArr.length - 1];
        const y = drawTop + ((depth - dMin) / ((dMax - dMin) || 1)) * (nDepths * cellH);
        if (y < drawTop || y > drawTop + nDepths * cellH) return;
        ctx.save();
        ctx.strokeStyle = '#ff4d4f';
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(startX, y);
        ctx.lineTo(totalW - 10, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#ff4d4f';
        ctx.font = '11px JetBrains Mono';
        ctx.textAlign = 'left';
        ctx.fillText(`${depth.toFixed(1)} ft`, startX + 6, y - 6);
        ctx.restore();
    }

    // ─── Sprint 28: Synthetic Seismogram ────────────────────────
    async runSeismic() {
        if (!this.currentWell) { GeoToast.warn('Select a well first'); return; }
        const freq = document.getElementById('seismicFreq')?.value || 30;
        const polarity = document.getElementById('seismicPolarity')?.value || 'normal';
        const phase = parseInt(document.getElementById('seismicPhase')?.value || '0', 10);
        GeoLoading.show('Generating synthetic seismogram...');
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/synthetic-seismogram`, {
                method: 'POST',
                body: JSON.stringify({ wavelet_freq: parseFloat(freq), polarity, phase })
            });
            this._renderSeismic(data);
        } catch (e) {
            GeoToast.error('Seismogram failed: ' + e.message);
        } finally { GeoLoading.hide(); }
    }

    _renderSeismic(data) {
        const container = document.getElementById('seismicResults');
        if (!container) return;

        let html = `<div style="display:flex;gap:20px;margin-bottom:16px;flex-wrap:wrap">
            <div class="stats-card" style="flex:1">
                <h4 style="color:var(--accent)">Acoustic Impedance</h4>
                <div class="petro-stat"><span>Min</span><strong>${data.stats.ai_min}</strong></div>
                <div class="petro-stat"><span>Max</span><strong>${data.stats.ai_max}</strong></div>
                <div class="petro-stat"><span>Mean</span><strong>${data.stats.ai_mean}</strong></div>
            </div>
            <div class="stats-card" style="flex:1">
                <h4 style="color:var(--accent)">Reflection Coefficients</h4>
                <div class="petro-stat"><span>Min</span><strong>${data.stats.rc_min}</strong></div>
                <div class="petro-stat"><span>Max</span><strong>${data.stats.rc_max}</strong></div>
                <div class="petro-stat"><span>Points</span><strong>${data.params.n_points}</strong></div>
            </div>
            <div class="stats-card" style="flex:1">
                <h4 style="color:var(--accent)">Wavelet</h4>
                <div class="petro-stat"><span>Frequency</span><strong>${data.params.wavelet_freq} Hz</strong></div>
                <div class="petro-stat"><span>Polarity</span><strong>${data.params.polarity}</strong></div>
                <div class="petro-stat"><span>Phase</span><strong>${data.params.phase}°</strong></div>
                <div class="petro-stat"><span>Type</span><strong>Ricker</strong></div>
            </div>
            <div class="stats-card" style="flex:1">
                <h4 style="color:var(--accent)">Time-Depth</h4>
                <div class="petro-stat"><span>TWT Min</span><strong>${data.stats.twt_min_s}s</strong></div>
                <div class="petro-stat"><span>TWT Max</span><strong>${data.stats.twt_max_s}s</strong></div>
                <div class="petro-stat"><span>Samples</span><strong>${data.params.n_points}</strong></div>
            </div>
        </div>`;
        html += '<canvas id="seismicCanvas" style="width:100%;height:560px;background:var(--bg-primary);border-radius:8px"></canvas>';

        container.innerHTML = html;
        container.className = '';
        container.style.padding = '0';

        // Render traces
        setTimeout(() => {
            const canvas = document.getElementById('seismicCanvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const W = canvas.parentElement.getBoundingClientRect().width;
            canvas.width = W * 2;
            canvas.height = 1120;
            ctx.scale(2, 2);
            const H = 560;
            const pad = { top: 20, right: 20, bottom: 40, left: 60 };
            const pw = W - pad.left - pad.right;
            const ph = H - pad.top - pad.bottom;

            ctx.fillStyle = '#0a0e14';
            ctx.fillRect(0, 0, W, H);

            const depth = data.depth;
            const twt = data.twt || [];
            const dMin = Math.min(...depth);
            const dMax = Math.max(...depth);

            // Grid
            ctx.strokeStyle = 'rgba(42,52,70,0.5)';
            ctx.lineWidth = 0.5;
            for (let i = 0; i <= 5; i++) {
                const y = pad.top + (ph / 5) * i;
                ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + pw, y); ctx.stroke();
                ctx.fillStyle = '#6b7a8d';
                ctx.font = '10px JetBrains Mono';
                ctx.textAlign = 'right';
                ctx.fillText((dMin + (dMax - dMin) / 5 * i).toFixed(0), pad.left - 8, y + 4);
            }

            // AI track (left quarter)
            const aiW = pw * 0.25;
            const aiMin = data.stats.ai_min;
            const aiMax = data.stats.ai_max;
            ctx.strokeStyle = '#5b8fb9';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            for (let i = 0; i < depth.length; i++) {
                const x = pad.left + ((data.ai[i] - aiMin) / ((aiMax - aiMin) || 1)) * aiW;
                const y = pad.top + ((depth[i] - dMin) / (dMax - dMin)) * ph;
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.stroke();

            // Synthetic trace (center-left) — wiggle + variable density
            const synthW = pw * 0.35;
            const synthLeft = pad.left + aiW + 12;
            const synthCenter = synthLeft + synthW / 2;
            const synthMax = Math.max(...data.synthetic.map(Math.abs)) || 1;

            // Variable density background
            for (let i = 1; i < depth.length; i++) {
                const amp = data.synthetic[i] / synthMax;
                const shade = Math.floor(128 + amp * 110);
                ctx.strokeStyle = `rgb(${shade},${shade},${shade})`;
                const y = pad.top + ((depth[i] - dMin) / (dMax - dMin)) * ph;
                ctx.beginPath();
                ctx.moveTo(synthLeft, y);
                ctx.lineTo(synthLeft + synthW, y);
                ctx.stroke();
            }

            ctx.strokeStyle = '#d4a853';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            for (let i = 0; i < depth.length; i++) {
                const x = synthCenter + (data.synthetic[i] / synthMax) * synthW / 2;
                const y = pad.top + ((depth[i] - dMin) / (dMax - dMin)) * ph;
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.stroke();

            // Fill positive
            ctx.fillStyle = 'rgba(212,168,83,0.15)';
            ctx.beginPath();
            ctx.moveTo(synthCenter, pad.top);
            for (let i = 0; i < depth.length; i++) {
                const x = synthCenter + (data.synthetic[i] / synthMax) * synthW / 2;
                const y = pad.top + ((depth[i] - dMin) / (dMax - dMin)) * ph;
                ctx.lineTo(Math.max(x, synthCenter), y);
            }
            ctx.lineTo(synthCenter, pad.top + ph);
            ctx.closePath();
            ctx.fill();

            // TWT-depth curve (right-mid)
            const twtW = pw * 0.2;
            const twtX0 = synthLeft + synthW + 14;
            const twtMin = twt.length ? Math.min(...twt) : 0;
            const twtMax = twt.length ? Math.max(...twt) : 1;
            ctx.strokeStyle = '#79c0ff';
            ctx.lineWidth = 1.4;
            ctx.beginPath();
            for (let i = 0; i < depth.length; i++) {
                const tx = twtX0 + (((twt[i] || 0) - twtMin) / ((twtMax - twtMin) || 1)) * twtW;
                const y = pad.top + ((depth[i] - dMin) / (dMax - dMin)) * ph;
                if (i === 0) ctx.moveTo(tx, y); else ctx.lineTo(tx, y);
            }
            ctx.stroke();

            // Wavelet display (far right)
            const wltW = pw * 0.18;
            const wltX0 = twtX0 + twtW + 14;
            const wlt = data.wavelet?.amplitude || [];
            const wltT = data.wavelet?.time || [];
            const wltCenterX = wltX0 + wltW / 2;
            const wltMax = Math.max(...wlt.map(Math.abs), 1e-9);
            const wltTop = pad.top + 40;
            const wltH = ph - 80;
            ctx.strokeStyle = '#ff7b72';
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            for (let i = 0; i < wlt.length; i++) {
                const x = wltCenterX + (wlt[i] / wltMax) * (wltW / 2 - 2);
                const y = wltTop + (i / Math.max(1, wlt.length - 1)) * wltH;
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.stroke();
            ctx.strokeStyle = 'rgba(255,123,114,0.3)';
            ctx.beginPath();
            ctx.moveTo(wltCenterX, wltTop);
            ctx.lineTo(wltCenterX, wltTop + wltH);
            ctx.stroke();

            // Labels
            ctx.fillStyle = '#9aa8b8';
            ctx.font = '12px Geologica';
            ctx.textAlign = 'center';
            ctx.fillText('AI', pad.left + aiW / 2, pad.top - 5);
            ctx.fillText('Synthetic', synthCenter, pad.top - 5);
            ctx.fillText('TWT(s)', twtX0 + twtW / 2, pad.top - 5);
            ctx.fillText('Wavelet', wltCenterX, pad.top - 5);

            if (wltT.length) {
                ctx.textAlign = 'left';
                ctx.font = '10px JetBrains Mono';
                ctx.fillStyle = '#6b7a8d';
                ctx.fillText(`${(Math.min(...wltT) * 1000).toFixed(1)} ms`, wltX0, wltTop + wltH + 14);
                ctx.fillText(`${(Math.max(...wltT) * 1000).toFixed(1)} ms`, wltX0 + wltW - 46, wltTop + wltH + 14);
            }

            const baseImage = ctx.getImageData(0, 0, canvas.width, canvas.height);
            this._seismicSyncCtx = { ctx, W, H, pad, ph, dMin, dMax, baseImage };
            if (Number.isFinite(this.depthSync?.activeDepth)) this._drawSeismicDepthMarker(this.depthSync.activeDepth);

            canvas.onmousemove = (ev) => {
                const rect = canvas.getBoundingClientRect();
                const y = ev.clientY - rect.top;
                const depth = dMin + ((y - pad.top) / (ph || 1)) * (dMax - dMin);
                this._publishDepthSync(depth, 'seismic');
            };
        }, 100);
    }

    // ─── Sprint 28: Offset-Well Analogs ─────────────────────────
    async runAnalogs() {
        if (!this.currentWell || !this.projects.length) { GeoToast.warn('Select a well first'); return; }
        GeoLoading.show('Finding analog wells...');
        try {
            const pid = this.projects[0]?.id;
            const resp = await fetch(`/api/projects/${pid}/well-analogs?reference_well_id=${this.currentWell.id}`, { headers: this._authHeaders() });
            const data = await resp.json();
            GeoLoading.hide();
            if (data.detail) { GeoToast.error(data.detail); return; }
            this._renderAnalogs(data);
        } catch (e) {
            GeoLoading.hide();
            GeoToast.error('Analog search failed');
        }
    }

    _renderAnalogs(data) {
        const container = document.getElementById('analogsResults');
        if (!container) return;

        let html = `<div style="margin-bottom:16px"><span style="color:var(--accent);font-weight:600">Reference: ${data.reference_well}</span></div>`;

        if (!data.analogs.length) {
            html += '<div style="color:var(--text-muted);padding:20px;text-align:center">No other wells with matching curves found</div>';
        } else {
            html += '<table class="petro-table"><tr><th>Well</th><th>Similarity</th><th>Curves</th><th>GR Mean</th><th>RT Mean</th><th>NPHI Mean</th><th>RHOB Mean</th></tr>';
            data.analogs.forEach(a => {
                const sim = (a.similarity * 100).toFixed(1);
                const simColor = a.similarity > 0.8 ? 'var(--success)' : a.similarity > 0.5 ? 'var(--warning)' : 'var(--text-muted)';
                html += `<tr>
                    <td style="font-weight:600">${a.well_name}</td>
                    <td style="color:${simColor};font-weight:600">${sim}%</td>
                    <td>${a.matching_curves}</td>
                    <td>${a.stats.GR?.mean?.toFixed(1) || '—'}</td>
                    <td>${a.stats.RT?.mean?.toFixed(1) || '—'}</td>
                    <td>${a.stats.NPHI?.mean?.toFixed(3) || '—'}</td>
                    <td>${a.stats.RHOB?.mean?.toFixed(2) || '—'}</td>
                </tr>`;
            });
            html += '</table>';
        }

        container.innerHTML = html;
        container.className = '';
        container.style.padding = '0';
    }

    // ─── Sprint 28: Users Management ────────────────────────────





    // ═══ Professional Petrophysics Engine (Sprint 29) ═══










    // ═══ Professional Features Sprint 31 ═══
    
    // Feature 4: Keyboard Navigation Pro
    _initProKeyboard() {
        document.addEventListener('keydown', (e) => {
            const isTyping = ['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName);
            if (isTyping) return;
            const key = e.key.toLowerCase();
            const range = this.renderer ? (this.renderer.viewStop - this.renderer.viewStart) : 100;
            const step = range * 0.1;
            const pageStep = range * 0.8;
            
            switch(key) {
                case 'g': this._toggleCurveTrack('GR'); e.preventDefault(); break;
                case 'r': if (!e.ctrlKey) { this._toggleCurveTrack('RT'); e.preventDefault(); } break;
                case 'p': this._toggleCurveTrack('NPHI'); e.preventDefault(); break;
                case 'arrowdown':
                    if (this.renderer) {
                        this.renderer.viewStart += step;
                        this.renderer.viewStop += step;
                        this.renderer.requestRender();
                        this.renderer._updateDepthInputs();
                    }
                    e.preventDefault(); break;
                case 'arrowup':
                    if (this.renderer) {
                        this.renderer.viewStart -= step;
                        this.renderer.viewStop -= step;
                        this.renderer.requestRender();
                        this.renderer._updateDepthInputs();
                    }
                    e.preventDefault(); break;
                case 'pagedown':
                    if (this.renderer) {
                        this.renderer.viewStart += pageStep;
                        this.renderer.viewStop += pageStep;
                        this.renderer.requestRender();
                        this.renderer._updateDepthInputs();
                    }
                    e.preventDefault(); break;
                case 'pageup':
                    if (this.renderer) {
                        this.renderer.viewStart -= pageStep;
                        this.renderer.viewStop -= pageStep;
                        this.renderer.requestRender();
                        this.renderer._updateDepthInputs();
                    }
                    e.preventDefault(); break;
                case '=': case '+':
                    if (this.renderer) {
                        const mid = (this.renderer.viewStart + this.renderer.viewStop) / 2;
                        const newRange = range * 0.7;
                        this.renderer.viewStart = mid - newRange/2;
                        this.renderer.viewStop = mid + newRange/2;
                        this.renderer.requestRender();
                        this.renderer._updateDepthInputs();
                    }
                    e.preventDefault(); break;
                case '-':
                    if (this.renderer) {
                        const mid = (this.renderer.viewStart + this.renderer.viewStop) / 2;
                        const newRange = range * 1.4;
                        this.renderer.viewStart = mid - newRange/2;
                        this.renderer.viewStop = mid + newRange/2;
                        this.renderer.requestRender();
                        this.renderer._updateDepthInputs();
                    }
                    e.preventDefault(); break;
                case 'home':
                    if (this.renderer && this.renderer.depthData?.length) {
                        this.renderer.viewStart = this.renderer.depthData[0];
                        this.renderer.viewStop = this.renderer.viewStart + range;
                        this.renderer.requestRender();
                        this.renderer._updateDepthInputs();
                    }
                    e.preventDefault(); break;
                case 'end':
                    if (this.renderer && this.renderer.depthData?.length) {
                        this.renderer.viewStop = this.renderer.depthData[this.renderer.depthData.length-1];
                        this.renderer.viewStart = this.renderer.viewStop - range;
                        this.renderer.requestRender();
                        this.renderer._updateDepthInputs();
                    }
                    e.preventDefault(); break;
            }
        });
    }
    
    _toggleCurveTrack(curve) {
        // Toggle visibility of a curve type in the viewer
        const cfg = this.renderer?.curveConfig;
        if (!cfg) return;
        for (const [mnem, c] of Object.entries(cfg)) {
            if (mnem === curve || mnem.startsWith(curve)) {
                c.hidden = !c.hidden;
            }
        }
        this.renderer?.requestRender();
    }

    // Feature 5: Session Save/Restore
    

    // Feature 6: Batch Export All Wells

    // Feature 9: Dark/Light Theme Toggle
    _currentTheme = 'dark';

    // Feature 10: Well Thumbnail Preview
    _initThumbnailPreview() {
        const sidebar = document.getElementById('wellList') || document.querySelector('.sidebar');
        if (!sidebar) return;
        this._thumbCanvas = document.createElement('canvas');
        this._thumbCanvas.width = 200; this._thumbCanvas.height = 120;
        this._thumbCanvas.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;border:1px solid #30363d;border-radius:6px;background:#0d1117;display:none;box-shadow:0 4px 12px rgba(0,0,0,0.5)';
        document.body.appendChild(this._thumbCanvas);
        
        sidebar.addEventListener('mouseover', (e) => {
            const wellItem = e.target.closest('[data-well-id]');
            if (!wellItem) return;
            const wellId = wellItem.dataset.wellId;
            if (!wellId) return;
            this._showThumbnail(wellId, e);
        });
        sidebar.addEventListener('mouseout', (e) => {
            const wellItem = e.target.closest('[data-well-id]');
            if (wellItem) this._thumbCanvas.style.display = 'none';
        });
    }
    
    async _showThumbnail(wellId, e) {
        // Mini GR curve preview
        try {
            const runs = await this._api(`/wells/${wellId}/log-runs`);
            if (!runs.length) return;
            const run = runs[runs.length-1];
            const resp = await fetch(`/api/log-runs/${run.id}/data-decimated?max_points=200&curve_mnemonics=GR`, { headers: this._authHeaders() });
            if (!resp.ok) return;
            const data = await resp.json();
            const gr = data.GR || data.data?.GR || [];
            if (gr.length < 2) return;
            
            const canvas = this._thumbCanvas;
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, 200, 120);
            ctx.fillStyle = '#0d1117';
            ctx.fillRect(0, 0, 200, 120);
            
            // Draw mini GR curve
            const min = Math.min(...gr.filter(v => v != null));
            const max = Math.max(...gr.filter(v => v != null));
            ctx.strokeStyle = '#2ea043';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            for (let i = 0; i < gr.length; i++) {
                if (gr[i] == null) continue;
                const x = 10 + ((gr[i] - min) / (max - min || 1)) * 180;
                const y = 5 + (i / gr.length) * 110;
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.stroke();
            
            // Label
            ctx.fillStyle = '#8b949e';
            ctx.font = '9px IBM Plex Mono';
            ctx.fillText('GR preview', 5, 118);
            
            canvas.style.display = 'block';
            canvas.style.left = (e.clientX + 15) + 'px';
            canvas.style.top = (e.clientY - 60) + 'px';
        } catch(e) {}
    }

    // Feature 11: Recent Wells & Favorites
    _initFavorites() {
        this._favorites = JSON.parse(localStorage.getItem('geolog_favorites') || '[]');
        this._recentWells = JSON.parse(localStorage.getItem('geolog_recent') || '[]');
    }
    
    toggleFavorite(wellId) {
        const idx = this._favorites.indexOf(wellId);
        if (idx >= 0) this._favorites.splice(idx, 1);
        else this._favorites.push(wellId);
        localStorage.setItem('geolog_favorites', JSON.stringify(this._favorites));
        this._renderWellSidebar();
    }
    
    addRecentWell(wellId, wellName) {
        this._recentWells = this._recentWells.filter(r => r.id !== wellId);
        this._recentWells.unshift({id: wellId, name: wellName, time: Date.now()});
        if (this._recentWells.length > 5) this._recentWells = this._recentWells.slice(0, 5);
        localStorage.setItem('geolog_recent', JSON.stringify(this._recentWells));
    }
    
    _renderWellSidebar() {
        // Add favorites section to sidebar
        const sidebar = document.querySelector('.sidebar') || document.querySelector('#wellList')?.parentElement;
        if (!sidebar) return;
        let favSection = document.getElementById('favoritesSection');
        if (!favSection) {
            favSection = document.createElement('div');
            favSection.id = 'favoritesSection';
            favSection.style.cssText = 'padding:6px 10px;border-bottom:1px solid #30363d';
            sidebar.insertBefore(favSection, sidebar.children[2] || null);
        }
        const favWells = (this.wells || []).filter(w => this._favorites.includes(w.id));
        const recent = this._recentWells || [];
        let html = '';
        if (favWells.length > 0) {
            html += '<div style="font-size:10px;color:#8b949e;margin-bottom:4px">⭐ Favorites</div>';
            for (const w of favWells) {
                html += '<span style="cursor:pointer;color:#f0883e;font-size:11px;margin-right:8px" data-action="app.selectWell" data-args="[' + w.id + ']">' + escapeHtml(w.name) + '</span>';
            }
        }
        if (recent.length > 0) {
            html += '<div style="font-size:10px;color:#8b949e;margin-top:4px">🕐 Recent</div>';
            for (const r of recent) {
                html += '<span style="cursor:pointer;color:#58a6ff;font-size:11px;margin-right:8px" data-action="app.selectWell" data-args="[' + r.id + ']">' + escapeHtml(r.name) + '</span>';
            }
        }
        favSection.innerHTML = html;
    }

    // Feature 8: Quick-add top via double-click (UI handler)
    _initDoubleClickTop() {
        if (this.renderer) {
            this.renderer.onDoubleClick = async (depth) => {
                const name = prompt('Formation name at ' + depth.toFixed(1) + ':');
                if (!name) return;
                try {
                    await this._api(`/wells/${this.currentWell.id}/tops`, {
                        method: 'POST', body: JSON.stringify({formation_name: name, depth: depth})
                    });
                    await this._loadTops();
                    this.renderer.requestRender();
                    GeoToast.success('Top added: ' + name + ' @ ' + depth.toFixed(1));
                } catch(e) {
                    GeoToast.error('Failed: ' + e.message);
                }
            };
        }
    }


    // ─── Tier 1 Panel Initializers ──────────────────────────────
    _initAdvancedQC() {
        const el = document.getElementById('advancedQCDashboard');
        if (!el) return;
        if (typeof AdvancedQCPanel !== 'undefined') {
            if (!this._qcPanel) this._qcPanel = new AdvancedQCPanel({ qcContentId: 'advancedQCDashboard', renderer: this.renderer });
            this._qcPanel.load(this.currentWell.id);
        } else {
            el.innerHTML = '<div style="padding:20px;color:#8b949e">Advanced QC module not loaded.</div>';
        }
    }

    _initZonation() {
        const el = document.getElementById('zonationDashboard');
        if (!el) return;
        if (typeof ZoneReportPanel !== 'undefined') {
            if (!this._znPanel) this._znPanel = new ZoneReportPanel('zonationDashboard');
            this._znPanel.render(this.currentWell.id);
        } else {
            el.innerHTML = '<div style="padding:20px;color:#8b949e">Zonation module not loaded.</div>';
        }
    }

    _initUnits() {
        const el = document.getElementById('unitsDashboard');
        if (!el) return;
        if (typeof UnitNormalizationPanel !== 'undefined') {
            if (!this._unitPanel) this._unitPanel = new UnitNormalizationPanel('unitsDashboard');
            this._unitPanel.render(this.currentWell.id);
        } else {
            el.innerHTML = '<div style="padding:20px;color:#8b949e">Unit normalization module not loaded.</div>';
        }
    }

    _initTemplates() {
        const el = document.getElementById('templatesDashboard');
        if (!el) return;
        if (typeof TemplateWorkflowPanel !== 'undefined') {
            if (!this._tmplPanel) this._tmplPanel = new TemplateWorkflowPanel('templatesDashboard');
            this._tmplPanel.render(this.currentWell.id);
        } else {
            el.innerHTML = '<div style="padding:20px;color:#8b949e">Template workflow module not loaded.</div>';
        }
    }

    // ─── Feature 1: Curve Scale Editor ────────────────────
    _initCurveScaleEditor() {
        if (!this.renderer) return;
        this.renderer.onCurveScaleEdit = (mnemonic, trackIdx) => {
            const cfg = this.curveConfig[mnemonic] || {};
            const scale = cfg.scale || [0, 100];
            const isLog = !!cfg.log;
            const isReverse = scale[0] > scale[1];

            const html = `
                <div style="padding:16px;min-width:280px">
                    <h3 style="margin:0 0 12px;color:#58a6ff;font-size:14px">Edit Scale: ${mnemonic}</h3>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
                        <label style="color:#8b949e;font-size:11px">Min
                            <input type="number" id="scaleMinInput" value="${isReverse ? scale[1] : scale[0]}" step="any" style="width:100%;background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:6px;margin-top:2px">
                        </label>
                        <label style="color:#8b949e;font-size:11px">Max
                            <input type="number" id="scaleMaxInput" value="${isReverse ? scale[0] : scale[1]}" step="any" style="width:100%;background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:6px;margin-top:2px">
                        </label>
                    </div>
                    <div style="display:flex;gap:12px;margin-bottom:12px">
                        <label style="color:#8b949e;font-size:11px;display:flex;align-items:center;gap:4px">
                            <input type="checkbox" id="scaleLogCheck" ${isLog ? 'checked' : ''}> Log scale
                        </label>
                        <label style="color:#8b949e;font-size:11px;display:flex;align-items:center;gap:4px">
                            <input type="checkbox" id="scaleReverseCheck" ${isReverse ? 'checked' : ''}> Reversed
                        </label>
                    </div>
                    <div style="display:flex;gap:8px;justify-content:flex-end">
                        <button data-action="GeoModal.close" style="background:#30363d;color:#c9d1d9;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;font-size:12px">Cancel</button>
                        <button id="scaleApplyBtn" style="background:#238636;color:#fff;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;font-size:12px">Apply</button>
                    </div>
                </div>`;

            GeoModal.show(html);
            document.getElementById('scaleApplyBtn')?.addEventListener('click', () => {
                const minVal = parseFloat(document.getElementById('scaleMinInput').value);
                const maxVal = parseFloat(document.getElementById('scaleMaxInput').value);
                const logCheck = document.getElementById('scaleLogCheck').checked;
                const reverseCheck = document.getElementById('scaleReverseCheck').checked;
                if (!isFinite(minVal) || !isFinite(maxVal)) { GeoToast.warn('Invalid values'); return; }
                if (!this.curveConfig[mnemonic]) this.curveConfig[mnemonic] = {};
                this.curveConfig[mnemonic].scale = reverseCheck ? [maxVal, minVal] : [minVal, maxVal];
                this.curveConfig[mnemonic].log = logCheck;
                this.renderer.curveConfig = this.curveConfig;
                this.renderer.render();
                GeoModal.close();
                GeoToast.info(`Scale updated: ${mnemonic}`);
            });
        };
    }

    // ─── Feature 2: Auto-Scale ────────────────────────────
    _autoScale() {
        if (!this.renderer || !this.renderer.curveData) return;
        const data = this.renderer.curveData;
        let updated = 0;
        for (const [mnemonic, values] of Object.entries(data)) {
            if (!values || values.length === 0) continue;
            const valid = values.filter(v => v != null && !isNaN(v) && isFinite(v));
            if (valid.length < 10) continue;
            valid.sort((a, b) => a - b);
            const p1 = valid[Math.floor(valid.length * 0.01)];
            const p99 = valid[Math.floor(valid.length * 0.99)];
            const range = p99 - p1;
            if (range <= 0) continue;
            if (!this.curveConfig[mnemonic]) this.curveConfig[mnemonic] = {};
            this.curveConfig[mnemonic].scale = [p1 - range * 0.05, p99 + range * 0.05];
            updated++;
        }
        this.renderer.curveConfig = this.curveConfig;
        this.renderer.render();
        GeoToast.info(`Auto-scaled ${updated} curves`);
    }

    // ─── Feature 6: Auto Lithology Toggle ─────────────────
    _toggleAutoLithology() {
        if (!this.renderer) return;
        this.renderer._showLithologyAuto = !this.renderer._showLithologyAuto;
        this.renderer.render();
        GeoToast.info(`Auto lithology: ${this.renderer._showLithologyAuto ? 'ON' : 'OFF'}`);
    }

    // ─── Feature 7: Core Data Overlay Toggle ──────────────
    _showCoreOverlay = false;

    async _toggleCoreOverlay() {
        if (!this.renderer || !this.currentWell) return;
        this._showCoreOverlay = !this._showCoreOverlay;
        this.renderer._showCoreOverlay = this._showCoreOverlay;
        if (this._showCoreOverlay && !this._coreDataLoaded) {
            try {
                const data = await this._api(`/wells/${this.currentWell.id}/core-data`);
                this.renderer.setCoreData(data?.points || data || []);
                this._coreDataLoaded = true;
            } catch {
                this.renderer.setCoreData([]);
                this._coreDataLoaded = true;
            }
        }
        this.renderer.render();
        GeoToast.info(`Core overlay: ${this._showCoreOverlay ? 'ON' : 'OFF'}`);
    }

    // ─── Feature 14: Depth Ruler Click-to-Pick ────────────
    _depthPickMode = false;

    _toggleDepthRulerPick() {
        this._depthPickMode = !this._depthPickMode;
        if (this.renderer) {
            this.renderer.canvas.style.cursor = this._depthPickMode ? 'crosshair' : 'default';
        }
        GeoToast.info(`Top pick mode: ${this._depthPickMode ? 'ON (click on ruler)' : 'OFF'}`);
        if (this._depthPickMode && this.renderer) {
            this._depthPickHandler = (e) => {
                if (!this._depthPickMode) return;
                const rect = this.renderer.canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                // Only respond to clicks in the depth ruler area
                if (x > this.renderer.margin.left + this.renderer.depthTrackWidth) return;
                const depth = this.renderer._yToDepth(y);
                if (depth < 0) return;
                const name = prompt(`Add formation top at ${depth.toFixed(1)} ft:`);
                if (!name) return;
                this._addFormationTop(depth, name);
            };
            this.renderer.canvas.addEventListener('click', this._depthPickHandler);
        } else if (!this._depthPickMode && this.renderer && this._depthPickHandler) {
            this.renderer.canvas.removeEventListener('click', this._depthPickHandler);
            this._depthPickHandler = null;
        }
    }

    async _addFormationTop(depth, name) {
        if (!this.currentWell) return;
        try {
            await this._api(`/wells/${this.currentWell.id}/tops`, {
                method: 'POST',
                body: JSON.stringify({ depth, name, formation_name: name }),
            });
            GeoToast.info(`Top added: ${name} at ${depth.toFixed(1)} ft`);
            if (typeof this._loadTops === 'function') await this._loadTops();
            if (this.renderer) this.renderer.render();
        } catch (e) {
            GeoToast.error('Failed to add top: ' + (e.message || e));
        }
    }

    // ─── Feature 15: Render Metrics ───────────────────────
    _showRenderMetrics() {
        if (!this.renderer) return;
        const m = this.renderer.getRenderMetrics();
        GeoModal.show(`
            <div style="padding:16px;min-width:300px">
                <h3 style="margin:0 0 12px;color:#58a6ff;font-size:14px">Render Metrics</h3>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
                    <div style="color:#8b949e">Total samples</div><div style="color:#c9d1d9;text-align:right">${m.total_samples.toLocaleString()}</div>
                    <div style="color:#8b949e">Visible samples</div><div style="color:#c9d1d9;text-align:right">${m.visible_samples.toLocaleString()}</div>
                    <div style="color:#8b949e">Rendered (stride ${m.stride})</div><div style="color:#c9d1d9;text-align:right">${m.rendered_samples.toLocaleString()}</div>
                    <div style="color:#8b949e">Zoom window</div><div style="color:#c9d1d9;text-align:right">${m.zoom_ft} ft</div>
                    <div style="color:#8b949e">View start</div><div style="color:#c9d1d9;text-align:right">${m.view_start.toFixed(1)} ft</div>
                    <div style="color:#8b949e">View stop</div><div style="color:#c9d1d9;text-align:right">${m.view_stop.toFixed(1)} ft</div>
                </div>
            </div>
        `);
    }

    // ─── Feature 17: Curve Legend Panel ────────────────────
    _showCurveLegend() {
        if (!this.renderer) return;
        const legend = this.renderer.getCurveLegend();
        if (!legend.length) { GeoToast.warn('No curves loaded'); return; }
        let html = `<div style="padding:16px;max-height:70vh;overflow-y:auto;min-width:400px">
            <h3 style="margin:0 0 12px;color:#58a6ff;font-size:14px">Curve Legend</h3>
            <table style="width:100%;border-collapse:collapse;font-size:11px">
            <tr style="color:#8b949e;border-bottom:1px solid #30363d">
                <th style="text-align:left;padding:4px">Color</th>
                <th style="text-align:left;padding:4px">Curve</th>
                <th style="text-align:left;padding:4px">Track</th>
                <th style="text-align:right;padding:4px">Scale</th>
                <th style="text-align:right;padding:4px">Samples</th>
                <th style="text-align:right;padding:4px">Mean</th>
            </tr>`;
        for (const c of legend) {
            const scaleStr = c.log ? `[${c.scale[0]}, ${c.scale[1]}] log` : `[${c.scale[0]}, ${c.scale[1]}]`;
            html += `<tr style="border-bottom:1px solid #21262d">
                <td style="padding:4px"><span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:${c.color}"></span></td>
                <td style="padding:4px;color:#c9d1d9;font-weight:bold">${escapeHtml(c.mnemonic)}</td>
                <td style="padding:4px;color:#8b949e">${c.track}</td>
                <td style="padding:4px;color:#8b949e;text-align:right">${scaleStr}</td>
                <td style="padding:4px;color:#8b949e;text-align:right">${c.samples.toLocaleString()}</td>
                <td style="padding:4px;color:#c9d1d9;text-align:right">${c.mean != null ? c.mean.toFixed(2) : '-'}</td>
            </tr>`;
        }
        html += '</table></div>';
        GeoModal.show(html);
    }

    // ─── Feature 18: Client Handoff Bundle ─────────────────

    // ─── Feature 19: Formation Lines Toggle ────────────────
    _toggleFormationLines() {
        if (!this.renderer) return;
        this.renderer._showFormationLines = !this.renderer._showFormationLines;
        this.renderer.render();
        GeoToast.info(`Formation lines: ${this.renderer._showFormationLines ? 'ON' : 'OFF'}`);
    }

    // ─── Wire up renderer callbacks ───────────────────────
    _wireRendererCallbacks() {
        if (!this.renderer) return;
        this._initCurveScaleEditor();
        this.renderer.onTrackResize = (widths) => {
            GeoToast.info('Track widths saved');
        };
        this.renderer.onCurveMoved = (mnemonic, from, to) => {
            GeoToast.info(`Moved ${mnemonic} → Track ${to + 1}`);
        };
        this.renderer.onDepthHover = (depth) => {
            this._publishDepthSync(depth, 'viewer');
        };
    }
}
