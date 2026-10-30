/**
 * SEG-Y upload, section preview and horizon picking for GeoLogApp.
 * Loaded after app.js and before bootstrap.js.
 */
Object.assign(GeoLogApp.prototype, {
    _segyProjectId() {
        return this.currentWell?.project_id || this.projects?.[0]?.id || null;
    },

    async uploadSeismic() {
        document.getElementById('segyFileInput')?.click();
    },

    async onSeismicFileSelected(event) {
        const file = event?.target?.files?.[0];
        if (!file) return;
        const projectId = this._segyProjectId();
        if (!projectId) {
            GeoToast.warn('Select a project first.');
            return;
        }
        const form = new FormData();
        form.append('file', file);
        form.append('name', file.name.replace(/\.(sgy|segy)$/i, ''));
        GeoLoading.show('Reading SEG-Y...');
        try {
            await this._api(`/projects/${projectId}/seismic`, { method: 'POST', body: form });
            GeoToast.success('SEG-Y uploaded');
            await this.loadSeismicLines();
        } catch (e) {
            GeoToast.error('SEG-Y upload failed: ' + e.message);
        } finally {
            GeoLoading.hide();
            if (event?.target) event.target.value = '';
        }
    },

    async loadSeismicLines() {
        const projectId = this._segyProjectId();
        const select = document.getElementById('segyLineSelect');
        if (!projectId || !select) return;
        try {
            const lines = await this._api(`/projects/${projectId}/seismic`);
            select.innerHTML = lines.map(line =>
                `<option value="${line.id}">${escapeHtml(line.name || line.filename || 'SEG-Y')} · ${line.trace_count} traces</option>`
            ).join('');
            if (lines.length) {
                await this.loadSeismicLine(select.value || lines[0].id);
            } else {
                this._segySection = null;
                this._drawSeismic();
            }
        } catch (e) {
            GeoToast.error('SEG-Y list failed: ' + e.message);
        }
    },

    async loadSeismicLine(lineId) {
        const id = Number(lineId || document.getElementById('segyLineSelect')?.value);
        if (!id) return;
        GeoLoading.show('Loading seismic section...');
        try {
            const [payload, horizons, faults, volume, links, surfaces] = await Promise.all([
                this._api(`/seismic/${id}/section?max_traces=600&max_samples=600`),
                this._api(`/seismic/${id}/horizons`),
                this._api(`/seismic/${id}/faults`),
                this._api(`/seismic/${id}/volume`),
                this._api(`/seismic/${id}/fault-links`),
                this._api(`/seismic/${id}/surfaces`),
            ]);
            this._segySection = payload.section;
            this._segyLine = payload.line;
            this._segyHorizons = horizons || [];
            this._segyFaults = faults || [];
            this._segyFaultLinks = links || [];
            this._segyVolume = volume || null;
            this._segyPicks = [];
            this._populateSeismicVolume(volume);
            this._drawSeismic();
            this._renderSeismicHorizonList();
            await this._populateSeismicSurfaces(surfaces);
            try {
                const models = await this._api(`/projects/${payload.line.project_id}/velocity-models`);
                this._populateVelocityModels(models);
            } catch (e) {
                this._populateVelocityModels([]);
            }
            await this.loadSeismicTies();
            await this.loadSeismicProspects();
            await this.loadProspectPortfolios();
            const status = document.getElementById('segyStatus');
            if (status) {
                const dimensions = volume?.is_3d ? ` · 3D ${volume.inline_count}×${volume.crossline_count}` : '';
                const total = payload.section.line_trace_count || payload.section.original_trace_count;
                const sampled = payload.section.sampled ? ` (${payload.section.original_trace_count} shown)` : '';
                status.textContent = `${total} traces${sampled} · ${payload.section.original_sample_count} samples · ${payload.line.sample_interval_ms} ms${dimensions}`;
            }
        } catch (e) {
            GeoToast.error('Seismic section failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    _populateSeismicVolume(volume) {
        const inline = document.getElementById('segyInlineSelect');
        const crossline = document.getElementById('segyCrosslineSelect');
        const info = document.getElementById('segyVolumeInfo');
        const is3d = Boolean(volume?.is_3d);
        if (inline) {
            inline.innerHTML = (volume?.inlines || []).map(value => `<option value="${value}">${value}</option>`).join('');
            inline.disabled = !is3d;
        }
        if (crossline) {
            crossline.innerHTML = (volume?.crosslines || []).map(value => `<option value="${value}">${value}</option>`).join('');
            crossline.disabled = !is3d;
        }
        if (info) {
            info.textContent = is3d
                ? `${volume.inline_count} inlines × ${volume.crossline_count} crosslines`
                : '2D line (no inline/crossline grid)';
        }
    },

    async loadProspectPortfolios() {
        const projectId = this._segyLine?.project_id;
        if (!projectId) {
            this._segyPortfolios = [];
            this._renderProspectPortfolioList();
            return;
        }
        try {
            this._segyPortfolios = await this._api(`/projects/${projectId}/prospect-portfolios`);
            this._renderProspectPortfolioList();
        } catch (e) {
            this._segyPortfolios = [];
            this._renderProspectPortfolioList();
        }
    },

    async buildProspectPortfolio() {
        const projectId = this._segyLine?.project_id;
        if (!projectId) return GeoToast.warn('Load a seismic line first.');
        if (!(this._segyProspects || []).length) return GeoToast.warn('Evaluate at least one prospect first.');
        const name = document.getElementById('portfolioName')?.value?.trim() || 'Portfolio';
        const price = Number(document.getElementById('portfolioPrice')?.value) || 60;
        const opex = Number(document.getElementById('portfolioOpex')?.value) || 0;
        const capex = Number(document.getElementById('portfolioCapex')?.value) || 0;
        const correlation = Number(document.getElementById('portfolioCorrelation')?.value) || 0;
        const riskCorrelation = Number(document.getElementById('portfolioRiskCorrelation')?.value) || 0;
        const capexTiming = document.getElementById('portfolioCapexTiming')?.value || 'success';
        GeoLoading.show('Building portfolio...');
        try {
            const portfolio = await this._api(`/projects/${projectId}/prospect-portfolios`, {
                method: 'POST',
                body: JSON.stringify({
                    name,
                    prospect_ids: this._segyProspects.map(item => item.id),
                    price_per_boe: price,
                    opex_per_boe: opex,
                    capex,
                    correlation,
                    risk_correlation: riskCorrelation,
                    capex_timing: capexTiming,
                    iterations: 2000,
                    seed: 42,
                }),
            });
            this._segyPortfolios = [portfolio, ...(this._segyPortfolios || [])];
            this._renderProspectPortfolioList();
            const result = portfolio.result?.portfolio || {};
            const status = document.getElementById('portfolioStatus');
            if (status) {
                status.textContent = `EMV ${Math.round(result.total_emv || 0).toLocaleString()} · P50 ${Math.round(result.total_boe_p50 || 0).toLocaleString()} BOE · risked ${Math.round(result.risked_boe_p50 || 0).toLocaleString()} BOE`;
            }
            GeoToast.success('Portfolio built');
        } catch (e) {
            GeoToast.error('Portfolio failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    _renderProspectPortfolioList() {
        const host = document.getElementById('portfolioList');
        if (!host) return;
        const rows = this._segyPortfolios || [];
        host.innerHTML = rows.length
            ? rows.map(portfolio => {
                const result = portfolio.result || {};
                const summary = result.portfolio || {};
                const top = (result.prospects || []).slice(0, 3).map(item =>
                    `${escapeHtml(item.name)} (${Math.round(item.emv).toLocaleString()})`
                ).join(', ');
                return `<div style="padding:2px 0"><strong>${escapeHtml(portfolio.name)}</strong> · EMV ${Math.round(summary.total_emv || 0).toLocaleString()} · BOE P90/P50/P10 ${Math.round(summary.total_boe_p90 || 0).toLocaleString()} / ${Math.round(summary.total_boe_p50 || 0).toLocaleString()} / ${Math.round(summary.total_boe_p10 || 0).toLocaleString()} · risked P50 ${Math.round(summary.risked_boe_p50 || 0).toLocaleString()} · top: ${top || '—'}</div>`;
            }).join('')
            : 'No portfolios built yet.';
    },

    async loadSeismicProspects() {
        const projectId = this._segyLine?.project_id;
        if (!projectId) {
            this._segyProspects = [];
            this._renderProspectList();
            return;
        }
        try {
            this._segyProspects = await this._api(`/projects/${projectId}/prospects`);
            this._renderProspectList();
        } catch (e) {
            this._segyProspects = [];
            this._renderProspectList();
        }
    },

    async createProspect() {
        const projectId = this._segyLine?.project_id;
        if (!projectId) return GeoToast.warn('Load a seismic line first.');
        const name = document.getElementById('prospectName')?.value?.trim() || 'Prospect';
        const surfaceId = Number(document.getElementById('prospectSurface')?.value);
        const baseSurfaceId = Number(document.getElementById('prospectBaseSurface')?.value) || null;
        const contact = Number(document.getElementById('prospectContact')?.value);
        if (!surfaceId) return GeoToast.warn('Build a surface first.');
        if (!(contact > 0)) return GeoToast.warn('Enter a contact depth in metres.');
        const porosity = Number(document.getElementById('prospectPorosity')?.value) || 0.2;
        const sw = Number(document.getElementById('prospectSw')?.value) || 0.3;
        const rf = Number(document.getElementById('prospectRf')?.value) || 0.35;
        const risk = Number(document.getElementById('prospectRisk')?.value) || 1;
        const fluidType = document.getElementById('prospectFluid')?.value || 'oil';
        const bg = Number(document.getElementById('prospectBg')?.value) || 0.005;
        const condensateYield = Number(document.getElementById('prospectYield')?.value) || 0;
        GeoLoading.show('Evaluating prospect...');
        try {
            const prospect = await this._api(`/projects/${projectId}/prospects`, {
                method: 'POST',
                body: JSON.stringify({
                    name,
                    surface_id: surfaceId,
                    base_surface_id: baseSurfaceId,
                    contact_depth_m: contact,
                    porosity,
                    water_saturation: sw,
                    recovery_factor: rf,
                    risk,
                    fluid_type: fluidType,
                    bg,
                    condensate_yield: condensateYield,
                    iterations: 2000,
                    seed: 42,
                }),
            });
            this._segyProspects = [prospect, ...(this._segyProspects || [])];
            this._renderProspectList();
            const result = prospect.result || {};
            const status = document.getElementById('prospectStatus');
            if (status) {
                const volume = result.stoiip?.p50_m3 != null
                    ? `STOIIP ${Math.round(result.stoiip.p50_m3).toLocaleString()} m³`
                    : `GIIP ${Math.round(result.giip?.p50_m3 || 0).toLocaleString()} m³ · BOE ${Math.round(result.boe?.p50_bbl || 0).toLocaleString()} bbl`;
                status.textContent = `GRV ${Math.round(prospect.grv_m3).toLocaleString()} m³ · ${volume}`;
            }
            GeoToast.success('Prospect evaluated');
        } catch (e) {
            GeoToast.error('Prospect failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    _renderProspectList() {
        const host = document.getElementById('prospectList');
        if (!host) return;
        const rows = this._segyProspects || [];
        host.innerHTML = rows.length
            ? rows.map(item => {
                const result = item.result || {};
                const volume = result.stoiip || result.giip || {};
                const label = result.fluid_type === 'oil' ? 'STOIIP' : 'GIIP';
                const extra = result.boe?.p50_bbl != null ? ` · BOE ${Math.round(result.boe.p50_bbl).toLocaleString()} bbl` : '';
                const risk = result.risk || {};
                return `<div style="padding:2px 0"><strong>${escapeHtml(item.name)}</strong> · ${escapeHtml(item.fluid_type || 'oil')} · GRV ${Math.round(item.grv_m3 || 0).toLocaleString()} m³ · ${label} P90/P50/P10 ${Math.round(volume.p90_m3 || 0).toLocaleString()} / ${Math.round(volume.p50_m3 || 0).toLocaleString()} / ${Math.round(volume.p10_m3 || 0).toLocaleString()} m³${extra} · risk ${Math.round((risk.probability ?? 1) * 100)}%</div>`;
            }).join('')
            : 'No prospects evaluated yet.';
    },

    async loadSeismicTies() {
        const wid = this.currentWell?.id;
        if (!wid) {
            this._segyTies = [];
            this._renderSeismicTieList();
            return;
        }
        try {
            const ties = await this._api(`/wells/${wid}/seismic-ties`);
            this._segyTies = (ties || []).filter(tie => tie.line_id === this._segyLine?.id);
            this._renderSeismicTieList();
        } catch (e) {
            this._segyTies = [];
            this._renderSeismicTieList();
        }
    },

    async createSeismicTie() {
        const wid = this.currentWell?.id;
        const line = this._segyLine;
        if (!wid) return GeoToast.warn('Select a well first.');
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        const inline = Number(document.getElementById('segyTieInline')?.value);
        const crossline = Number(document.getElementById('segyTieCrossline')?.value);
        const maxShift = Number(document.getElementById('segyTieMaxShift')?.value) || 40;
        const datum = Number(document.getElementById('segyTieDatum')?.value) || 0;
        if (!inline || !crossline) return GeoToast.warn('Enter the tie inline and crossline.');
        GeoLoading.show('Tying well to seismic...');
        try {
            const tie = await this._api(`/wells/${wid}/seismic-ties`, {
                method: 'POST',
                body: JSON.stringify({
                    line_id: line.id,
                    inline,
                    crossline,
                    max_shift_ms: maxShift,
                    datum_ms: datum,
                }),
            });
            this._segyTie = tie;
            this._segyTies = [tie, ...(this._segyTies || [])];
            this._drawSeismicTie();
            this._renderSeismicTieList();
            const status = document.getElementById('segyTieStatus');
            if (status) {
                status.textContent = `shift ${tie.shift_ms} ms · correlation ${tie.correlation}`;
            }
            GeoToast.success(`Tie created · shift ${tie.shift_ms} ms`);
        } catch (e) {
            GeoToast.error('Well tie failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    _renderSeismicTieList() {
        const host = document.getElementById('segyTieList');
        if (!host) return;
        const ties = this._segyTies || [];
        host.innerHTML = ties.length
            ? ties.map(tie => `<span style="margin-right:14px">${escapeHtml(tie.name)} · inline ${tie.inline}/${tie.crossline} · shift ${tie.shift_ms} ms · corr ${tie.correlation}</span>`).join('')
            : 'No well ties on this line.';
    },

    _drawSeismicTie() {
        const canvas = document.getElementById('segyTieCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);
        const result = this._segyTie?.result;
        if (!result?.twt_ms?.length) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '13px sans-serif';
            ctx.fillText('Create a well tie from a well, line and inline/crossline', 18, 28);
            return;
        }
        const times = result.twt_ms;
        const seismic = result.seismic;
        const synthetic = result.synthetic_shifted || result.synthetic;
        const left = 62;
        const right = w - 18;
        const top = 20;
        const bottom = h - 34;
        const plotW = right - left;
        const plotH = bottom - top;
        const tMin = Math.min(...times);
        const tMax = Math.max(...times);
        const norm = values => {
            const finite = values.filter(value => Number.isFinite(Number(value)));
            const min = Math.min(...finite);
            const max = Math.max(...finite);
            return { min, span: Math.max(1e-9, max - min) };
        };
        const sNorm = norm(seismic);
        const yNorm = norm(synthetic);
        const drawTrack = (values, x0, width, color, scale) => {
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            let started = false;
            values.forEach((value, index) => {
                const x = x0 + ((Number(value) - scale.min) / scale.span) * width;
                const y = top + ((times[index] - tMin) / Math.max(1e-9, tMax - tMin)) * plotH;
                if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
            });
            ctx.stroke();
        };
        drawTrack(seismic, left, plotW * 0.38, '#58a6ff', sNorm);
        drawTrack(synthetic, left + plotW * 0.52, plotW * 0.38, '#f78166', yNorm);
        ctx.strokeStyle = '#30363d';
        ctx.lineWidth = 1;
        ctx.strokeRect(left, top, plotW, plotH);
        ctx.fillStyle = '#8b949e';
        ctx.font = '11px sans-serif';
        ctx.fillText('seismic', left + 4, top + 12);
        ctx.fillText('synthetic', left + plotW * 0.52 + 4, top + 12);
        for (let index = 0; index <= 4; index += 1) {
            const value = tMin + (index / 4) * (tMax - tMin);
            const y = bottom - (index / 4) * plotH;
            ctx.fillText(`${Math.round(value)} ms`, 4, y + 4);
        }
        ctx.fillStyle = '#c9d1d9';
        ctx.fillText(`shift ${result.shift_ms} ms · corr ${result.correlation}${result.checkshot_used ? ' · checkshot' : ''}`, left + 4, h - 10);
    },

    _populateVelocityModels(models) {
        this._segyVelocityModels = models || [];
        const select = document.getElementById('segyVelocityModel');
        if (!select) return;
        select.innerHTML = this._segyVelocityModels.map(model =>
            `<option value="${model.id}">${escapeHtml(model.name)} · ${model.kind === 'constant' ? `${model.velocity_m_s} m/s` : `${(model.layers || []).length} layers`}</option>`
        ).join('');
    },

    async saveVelocityModel() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        const name = document.getElementById('segyVelocityName')?.value?.trim();
        const velocity = Number(document.getElementById('segyVelocity')?.value);
        if (!name) return GeoToast.warn('Velocity model name is required.');
        if (!(velocity >= 500 && velocity <= 8000)) return GeoToast.warn('Velocity must be between 500 and 8000 m/s.');
        try {
            await this._api(`/projects/${line.project_id}/velocity-models`, {
                method: 'POST',
                body: JSON.stringify({ name, kind: 'constant', velocity_m_s: velocity }),
            });
            const models = await this._api(`/projects/${line.project_id}/velocity-models`);
            this._populateVelocityModels(models);
            GeoToast.success('Velocity model added');
        } catch (e) {
            GeoToast.error('Velocity model failed: ' + e.message);
        }
    },

    async run3dMigration() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        const velocity = Number(document.getElementById('segyMigrationVelocity')?.value) || 2000;
        const maxInlines = Number(document.getElementById('segyMigrationInline')?.value) || 24;
        const maxCrosslines = Number(document.getElementById('segyMigrationCrossline')?.value) || 24;
        const inlineSpacing = Number(document.getElementById('segyInlineSpacing')?.value) || 25;
        const crosslineSpacing = Number(document.getElementById('segyCrosslineSpacing')?.value) || 25;
        GeoLoading.show('Running 3D Kirchhoff migration...');
        try {
            const migration = await this._api(`/seismic/${line.id}/migrate-3d`, {
                method: 'POST',
                body: JSON.stringify({
                    name: `Migration ${Math.round(velocity)} m/s`,
                    velocity_m_s: velocity,
                    inline_spacing_m: inlineSpacing,
                    crossline_spacing_m: crosslineSpacing,
                    max_inlines: maxInlines,
                    max_crosslines: maxCrosslines,
                    max_samples: 160,
                    max_depth_samples: 128,
                }),
            });
            const section = await this._api(`/seismic/${line.id}/migrations/${migration.id}/section`);
            this._segyMigration = migration;
            this._segyMigrationSection = section;
            this._drawMigratedSection();
            const status = document.getElementById('segyMigrationStatus');
            if (status) {
                status.textContent = `${migration.stats.inline_count}×${migration.stats.crossline_count}×${migration.stats.depth_count} · velocity ${migration.velocity_m_s} m/s`;
            }
            GeoToast.success('3D migration complete');
        } catch (e) {
            GeoToast.error('3D migration failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    _drawMigratedSection() {
        const canvas = document.getElementById('segyMigrationCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);
        const section = this._segyMigrationSection;
        if (!section?.data?.length) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '13px sans-serif';
            ctx.fillText('Run 3D migration to view a depth section', 18, 28);
            return;
        }
        const rows = section.data.length;
        const cols = section.data[0]?.length || 0;
        const left = 56;
        const right = w - 18;
        const top = 22;
        const bottom = h - 30;
        const plotW = right - left;
        const plotH = bottom - top;
        const values = section.data.flat().filter(value => Number.isFinite(Number(value)));
        const maxAbs = Math.max(...values.map(value => Math.abs(Number(value))), 1e-9);
        for (let y = 0; y < rows; y += 1) {
            for (let x = 0; x < cols; x += 1) {
                const norm = Math.max(-1, Math.min(1, Number(section.data[y][x]) / maxAbs));
                const red = norm >= 0 ? 255 : Math.round(60 * (1 + norm));
                const green = Math.round(120 * (1 - Math.abs(norm)));
                const blue = norm < 0 ? 255 : Math.round(60 * (1 - norm));
                ctx.fillStyle = `rgb(${red},${green},${blue})`;
                ctx.fillRect(
                    left + (x / cols) * plotW,
                    top + (y / rows) * plotH,
                    Math.ceil(plotW / cols) + 1,
                    Math.ceil(plotH / rows) + 1
                );
            }
        }
        ctx.strokeStyle = '#30363d';
        ctx.strokeRect(left, top, plotW, plotH);
        ctx.fillStyle = '#8b949e';
        ctx.font = '11px sans-serif';
        const depths = section.depths_m || [];
        for (let index = 0; index <= 4; index += 1) {
            const depth = depths[Math.round((index / 4) * Math.max(0, depths.length - 1))] ?? 0;
            const py = top + (index / 4) * plotH;
            ctx.fillText(`${depth} m`, 4, py + 4);
        }
        ctx.fillText(`${section.mode} ${section.value}`, left + 4, h - 10);
    },

    async addFenceSegment() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        const parse = value => String(value || '').split(',').map(item => Number(item.trim()));
        const start = parse(document.getElementById('fenceStart')?.value);
        const end = parse(document.getElementById('fenceEnd')?.value);
        if (start.length !== 2 || end.length !== 2 || start.some(value => !Number.isFinite(value)) || end.some(value => !Number.isFinite(value))) {
            return GeoToast.warn('Use inline,crossline for both fence ends.');
        }
        const inlineSpacing = Number(document.getElementById('segyInlineSpacing')?.value);
        const crosslineSpacing = Number(document.getElementById('segyCrosslineSpacing')?.value);
        const params = new URLSearchParams({
            inline1: String(start[0]),
            crossline1: String(start[1]),
            inline2: String(end[0]),
            crossline2: String(end[1]),
            max_traces: '600',
            max_samples: '600',
        });
        if (inlineSpacing > 0 && crosslineSpacing > 0) {
            params.set('inline_spacing_m', String(inlineSpacing));
            params.set('crossline_spacing_m', String(crosslineSpacing));
        }
        try {
            const fence = await this._api(`/seismic/${line.id}/arbitrary-line?${params.toString()}`);
            this._segyFences = [...(this._segyFences || []), fence];
            this._drawSeismicFences();
            const status = document.getElementById('fenceStatus');
            if (status) status.textContent = `${this._segyFences.length} fence segment(s)`;
            GeoToast.success('Fence segment added');
        } catch (e) {
            GeoToast.error('Fence failed: ' + e.message);
        }
    },

    clearFences() {
        this._segyFences = [];
        this._drawSeismicFences();
        const status = document.getElementById('fenceStatus');
        if (status) status.textContent = '';
    },

    _drawSeismicFences() {
        const canvas = document.getElementById('segyFenceCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);
        const fences = this._segyFences || [];
        if (!fences.length) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '13px sans-serif';
            ctx.fillText('Add an arbitrary line to build a fence diagram', 18, 28);
            return;
        }
        const gap = 12;
        const segmentWidth = (w - gap * (fences.length + 1)) / fences.length;
        fences.forEach((fence, fenceIndex) => {
            const rows = fence.data.length;
            const cols = fence.data[0]?.length || 0;
            if (!rows || !cols) return;
            const x0 = gap + fenceIndex * (segmentWidth + gap);
            const top = 28;
            const plotH = h - 58;
            const maxAbs = Math.max(Math.abs(fence.amplitude_min || 0), Math.abs(fence.amplitude_max || 1), 1e-9);
            for (let y = 0; y < rows; y += 1) {
                for (let x = 0; x < cols; x += 1) {
                    const norm = Math.max(-1, Math.min(1, (Number(fence.data[y][x]) || 0) / maxAbs));
                    ctx.fillStyle = norm >= 0
                        ? `rgba(255, ${Math.round(140 - norm * 60)}, ${Math.round(80 - norm * 40)}, 1)`
                        : `rgba(40, ${Math.round(120 + norm * 40)}, ${Math.round(180 + norm * 60)}, 1)`;
                    ctx.fillRect(
                        x0 + (x / cols) * segmentWidth,
                        top + (y / rows) * plotH,
                        Math.ceil(segmentWidth / cols) + 1,
                        Math.ceil(plotH / rows) + 1
                    );
                }
            }
            ctx.strokeStyle = '#30363d';
            ctx.strokeRect(x0, top, segmentWidth, plotH);
            ctx.fillStyle = '#c9d1d9';
            ctx.font = '11px sans-serif';
            ctx.fillText(`${fence.start?.inline}/${fence.start?.crossline} → ${fence.end?.inline}/${fence.end?.crossline}`, x0, 16);
            ctx.fillText(`${fence.labels?.[0] ?? 0} → ${fence.labels?.[fence.labels.length - 1] ?? 0} ${fence.label_name === 'distance_m' ? 'm' : ''}`, x0, h - 10);
        });
    },

    async buildCompartments() {
        const line = this._segyLine;
        const surface = this._segySurface;
        if (!line || !surface) return GeoToast.warn('Build or load a depth surface first.');
        const contact = Number(document.getElementById('segyCompartmentContact')?.value);
        const baseId = Number(document.getElementById('segyCompartmentBase')?.value) || null;
        if (!(contact > 0)) return GeoToast.warn('Enter a contact depth in metres.');
        try {
            const result = await this._api(`/seismic/${line.id}/surfaces/${surface.id}/compartments`, {
                method: 'POST',
                body: JSON.stringify({
                    contact_depth_m: contact,
                    base_surface_id: baseId,
                    fault_link_ids: (this._segyFaultLinks || []).map(link => link.id),
                }),
            });
            this._segyCompartments = result.compartments || [];
            this._renderCompartmentList();
            const status = document.getElementById('segyCompartmentStatus');
            if (status) {
                const juxtaposition = result.juxtaposition || {};
                const juxText = juxtaposition.faults ? ` · juxtaposition ${juxtaposition.reservoir_reservoir_samples} RR / ${juxtaposition.seal_samples} seal` : '';
                status.textContent = `${result.compartments.length} compartments · GRV ${Math.round(result.total_grv_m3).toLocaleString()} m³${juxText}`;
            }
            GeoToast.success('Compartments built');
        } catch (e) {
            GeoToast.error('Compartment build failed: ' + e.message);
        }
    },

    _renderCompartmentList() {
        const host = document.getElementById('segyCompartmentList');
        if (!host) return;
        const compartments = this._segyCompartments || [];
        host.innerHTML = compartments.length
            ? compartments.map(item => `<span style="margin-right:14px">C${item.id} · ${Math.round(item.grv_m3).toLocaleString()} m³ · ${Math.round(item.area_m2).toLocaleString()} m²</span>`).join('')
            : 'No compartments built yet.';
    },

    async convertSurfaceDepth() {
        const line = this._segyLine;
        const surface = this._segySurface;
        if (!line || !surface) return GeoToast.warn('Build or load a surface first.');
        const modelId = Number(document.getElementById('segyVelocityModel')?.value);
        if (!modelId) return GeoToast.warn('Add a velocity model first.');
        try {
            const updated = await this._api(`/seismic/${line.id}/surfaces/${surface.id}/depth`, {
                method: 'POST',
                body: JSON.stringify({ velocity_model_id: modelId }),
            });
            this._segySurface = updated;
            const domain = document.getElementById('segySurfaceDomain');
            if (domain) domain.value = 'depth';
            this._drawSeismicSurfaceMap();
            const status = document.getElementById('segySurfaceStatus');
            if (status) {
                const stats = updated.depth_stats || {};
                status.textContent = `${updated.name} · ${stats.min_depth_m}–${stats.max_depth_m} m`;
            }
            GeoToast.success('Surface converted to depth');
        } catch (e) {
            GeoToast.error('Depth conversion failed: ' + e.message);
        }
    },

    async _populateSeismicSurfaces(surfaces) {
        this._segySurfaces = surfaces || [];
        const select = document.getElementById('segySurfaceSelect');
        const prospectSelect = document.getElementById('prospectSurface');
        const baseSelect = document.getElementById('prospectBaseSurface');
        const compartmentBase = document.getElementById('segyCompartmentBase');
        const options = this._segySurfaces.map(surface =>
            `<option value="${surface.id}">${escapeHtml(surface.name)} · ${surface.stats?.point_count || 0} pts</option>`
        ).join('');
        if (select) select.innerHTML = options;
        if (prospectSelect) prospectSelect.innerHTML = options;
        if (baseSelect) baseSelect.innerHTML = '<option value="">No base</option>' + options;
        if (compartmentBase) compartmentBase.innerHTML = '<option value="">No base</option>' + options;
        if (this._segySurfaces.length) {
            const current = select?.value || this._segySurfaces[0].id;
            await this.loadSeismicSurface(current);
        } else {
            this._segySurface = null;
            this._drawSeismicSurfaceMap();
            const status = document.getElementById('segySurfaceStatus');
            if (status) status.textContent = 'No surfaces built yet.';
        }
    },

    async buildSeismicSurface() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a 3D SEG-Y volume first.');
        const name = document.getElementById('segySurfaceName')?.value?.trim() || 'Surface';
        const horizonName = document.getElementById('segySurfaceHorizon')?.value?.trim() || null;
        const inlineSpacing = Number(document.getElementById('segyInlineSpacing')?.value);
        const crosslineSpacing = Number(document.getElementById('segyCrosslineSpacing')?.value);
        const method = document.getElementById('segySurfaceMethod')?.value || 'idw';
        const anisotropy = Number(document.getElementById('segyKrigeAniso')?.value) || 1;
        const azimuth = Number(document.getElementById('segyKrigeAzimuth')?.value) || 0;
        GeoLoading.show('Building 3D surface...');
        try {
            const surface = await this._api(`/seismic/${line.id}/surfaces`, {
                method: 'POST',
                body: JSON.stringify({
                    name,
                    horizon_name: horizonName,
                    max_grid: 96,
                    method,
                    variogram: { model: 'spherical' },
                    anisotropy_ratio: anisotropy,
                    azimuth_deg: azimuth,
                    inline_spacing_m: inlineSpacing > 0 ? inlineSpacing : null,
                    crossline_spacing_m: crosslineSpacing > 0 ? crosslineSpacing : null,
                }),
            });
            this._segySurface = surface;
            await this._reloadSeismicSurfaces(surface.id);
            GeoToast.success(`Surface ${surface.name} built · ${surface.stats?.point_count || 0} picks`);
        } catch (e) {
            GeoToast.error('Surface build failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    async _reloadSeismicSurfaces(selectId) {
        const line = this._segyLine;
        if (!line) return;
        try {
            const surfaces = await this._api(`/seismic/${line.id}/surfaces`);
            this._segySurfaces = surfaces || [];
            const select = document.getElementById('segySurfaceSelect');
            const prospectSelect = document.getElementById('prospectSurface');
            const baseSelect = document.getElementById('prospectBaseSurface');
            const compartmentBase = document.getElementById('segyCompartmentBase');
            const options = this._segySurfaces.map(surface =>
                `<option value="${surface.id}">${escapeHtml(surface.name)} · ${surface.stats?.point_count || 0} pts</option>`
            ).join('');
            if (baseSelect) baseSelect.innerHTML = '<option value="">No base</option>' + options;
            if (compartmentBase) compartmentBase.innerHTML = '<option value="">No base</option>' + options;
            if (select) {
                select.innerHTML = options;
                if (selectId) select.value = String(selectId);
            }
            if (prospectSelect) {
                prospectSelect.innerHTML = options;
                if (selectId) prospectSelect.value = String(selectId);
            }
            if (selectId) await this.loadSeismicSurface(selectId);
            else this._drawSeismicSurfaceMap();
        } catch (e) {
            GeoToast.error('Surface list failed: ' + e.message);
        }
    },

    async loadSeismicSurface(surfaceId) {
        const line = this._segyLine;
        const id = Number(surfaceId || document.getElementById('segySurfaceSelect')?.value);
        if (!line || !id) return;
        try {
            this._segySurface = await this._api(`/seismic/${line.id}/surfaces/${id}`);
            this._segyCompartments = this._segySurface.compartments || [];
            this._renderCompartmentList();
            this._drawSeismicSurfaceMap();
            const status = document.getElementById('segySurfaceStatus');
            if (status) {
                const stats = this._segySurface.stats || {};
                status.textContent = `${this._segySurface.name} · ${stats.inline_count}×${stats.crossline_count} · coverage ${Math.round((stats.coverage || 0) * 100)}%`;
            }
        } catch (e) {
            GeoToast.error('Surface load failed: ' + e.message);
        }
    },

    _drawSeismicSurfaceMap() {
        const canvas = document.getElementById('segySurfaceMap');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);
        const surface = this._segySurface;
        const domain = document.getElementById('segySurfaceDomain')?.value || 'time';
        const depthGrid = surface?.depth_grid || [];
        const useDepth = domain === 'depth' && depthGrid.length > 0;
        const grid = useDepth ? depthGrid : surface?.grid;
        const unit = useDepth ? 'm' : 'ms';
        if (!surface?.grid?.length || !grid?.length) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '13px sans-serif';
            ctx.fillText('Build a surface from inline/crossline picks', 18, 28);
            return;
        }
        const rows = grid.length;
        const cols = grid[0]?.length || 0;
        if (!rows || !cols) return;
        const left = 52;
        const right = w - 18;
        const top = 18;
        const bottom = h - 30;
        const plotW = right - left;
        const plotH = bottom - top;
        const values = grid.flat().filter(value => Number.isFinite(Number(value)));
        const min = Math.min(...values);
        const max = Math.max(...values);
        const span = Math.max(1e-9, max - min);
        for (let row = 0; row < rows; row += 1) {
            for (let col = 0; col < cols; col += 1) {
                const value = Number(grid[row][col]);
                const t = Math.max(0, Math.min(1, (value - min) / span));
                const r = Math.round(32 + t * 208);
                const g = Math.round(96 + t * 48);
                const b = Math.round(196 - t * 150);
                ctx.fillStyle = `rgb(${r},${g},${b})`;
                ctx.fillRect(
                    left + (col / cols) * plotW,
                    top + (row / rows) * plotH,
                    Math.ceil(plotW / cols) + 1,
                    Math.ceil(plotH / rows) + 1
                );
            }
        }
        ctx.strokeStyle = '#30363d';
        ctx.lineWidth = 1;
        ctx.strokeRect(left, top, plotW, plotH);
        ctx.fillStyle = '#8b949e';
        ctx.font = '11px sans-serif';
        const inlines = surface.inlines || [];
        const crosslines = surface.crosslines || [];
        for (let index = 0; index <= 4; index += 1) {
            const gx = left + (index / 4) * plotW;
            const gy = bottom - (index / 4) * plotH;
            ctx.fillText(String(crosslines[Math.round((index / 4) * Math.max(0, crosslines.length - 1))] ?? ''), gx - 10, h - 10);
            ctx.fillText(String(inlines[Math.round((index / 4) * Math.max(0, inlines.length - 1))] ?? ''), 6, gy + 4);
        }
        ctx.fillText('crossline', right - 54, h - 10);
        ctx.save();
        ctx.translate(12, top + 34);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('inline', 0, 0);
        ctx.restore();
        ctx.fillStyle = '#c9d1d9';
        ctx.fillText(`${surface.name} · ${min.toFixed(1)}–${max.toFixed(1)} ${unit}`, left + 6, top + 14);
        for (const link of this._segyFaultLinks || []) {
            const ordered = (link.points || []).slice().sort((a, b) => Number(a.inline) - Number(b.inline));
            if (ordered.length < 2) continue;
            ctx.strokeStyle = link.color || '#f85149';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ordered.forEach((point, index) => {
                const inlineIndex = inlines.indexOf(Number(point.inline));
                const crosslineIndex = crosslines.indexOf(Number(point.crossline));
                if (inlineIndex < 0 || crosslineIndex < 0) return;
                const px = left + (crosslineIndex / Math.max(1, crosslines.length - 1)) * plotW;
                const py = top + (inlineIndex / Math.max(1, inlines.length - 1)) * plotH;
                if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
            });
            ctx.stroke();
        }
    },

    async loadSeismicInline() {
        const value = Number(document.getElementById('segyInlineSelect')?.value);
        await this.loadSeismicVolumeSection('inline', value);
    },

    async loadSeismicCrossline() {
        const value = Number(document.getElementById('segyCrosslineSelect')?.value);
        await this.loadSeismicVolumeSection('crossline', value);
    },

    async loadSeismicVolumeSection(mode, value) {
        const line = this._segyLine;
        if (!line || !value) return GeoToast.warn('Load a 3D SEG-Y volume first.');
        GeoLoading.show(`Loading ${mode} ${value}...`);
        try {
            const [payload, horizons, links] = await Promise.all([
                this._api(`/seismic/${line.id}/${mode}/${value}/section?max_traces=600&max_samples=600`),
                this._api(`/seismic/${line.id}/horizons`),
                this._api(`/seismic/${line.id}/fault-links`),
            ]);
            this._segySection = payload.section;
            this._segyHorizons = horizons || [];
            this._segyFaultLinks = links || [];
            this._segyPicks = [];
            this._drawSeismic();
            this._renderSeismicHorizonList();
            const status = document.getElementById('segyStatus');
            if (status) {
                status.textContent = `${mode} ${value} · ${payload.section.trace_count} traces by ${payload.section.label_name} · ${payload.section.original_sample_count} samples`;
            }
        } catch (e) {
            GeoToast.error(`Could not load ${mode} ${value}: ` + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    async linkSeismicFaults3D() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        if (!this._segyVolume?.is_3d) return GeoToast.warn('Upload a 3D volume with inline/crossline headers first.');
        GeoLoading.show('Linking faults across inline sections...');
        const inlineSpacing = Number(document.getElementById('segyInlineSpacing')?.value);
        const crosslineSpacing = Number(document.getElementById('segyCrosslineSpacing')?.value);
        const velocityModelId = Number(document.getElementById('segyVelocityModel')?.value);
        try {
            const result = await this._api(`/seismic/${line.id}/faults/link-3d`, {
                method: 'POST',
                body: JSON.stringify({
                    threshold: 0.35,
                    min_points: 4,
                    max_sections: 12,
                    crossline_tolerance: 3,
                    sample_tolerance: 16,
                    inline_spacing_m: inlineSpacing > 0 ? inlineSpacing : null,
                    crossline_spacing_m: crosslineSpacing > 0 ? crosslineSpacing : null,
                    velocity_model_id: velocityModelId > 0 ? velocityModelId : null,
                }),
            });
            this._segyFaultLinks = result.links || [];
            this._renderSeismicHorizonList();
            this._drawSeismic();
            GeoToast.success(result.links?.length
                ? `${result.links.length} 3D fault link(s) across ${result.scanned_inlines} inlines`
                : 'No 3D fault links found; try a lower threshold or more sections');
        } catch (e) {
            GeoToast.error('3D fault linking failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    _drawSeismic() {
        const canvas = document.getElementById('segyCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width, h = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);
        const section = this._segySection;
        if (!section?.data?.length) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '13px sans-serif';
            ctx.fillText('Upload a SEG-Y line to view a section', 18, 30);
            this._drawSeismicFaultMap();
            return;
        }
        const rows = section.data.length;
        const cols = section.data[0].length;
        const off = document.createElement('canvas');
        off.width = cols;
        off.height = rows;
        const offCtx = off.getContext('2d');
        const image = offCtx.createImageData(cols, rows);
        const maxAbs = Math.max(Math.abs(section.amplitude_min || 0), Math.abs(section.amplitude_max || 1), 1e-9);
        for (let y = 0; y < rows; y++) {
            for (let x = 0; x < cols; x++) {
                const value = Number(section.data[y][x]) || 0;
                const norm = Math.max(-1, Math.min(1, value / maxAbs));
                const idx = (y * cols + x) * 4;
                image.data[idx] = norm >= 0 ? 255 : Math.round(60 * (1 + norm));
                image.data[idx + 1] = Math.round(120 * (1 - Math.abs(norm)));
                image.data[idx + 2] = norm < 0 ? 255 : Math.round(60 * (1 - norm));
                image.data[idx + 3] = 255;
            }
        }
        offCtx.putImageData(image, 0, 0);
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(off, 0, 0, w, h);

        const drawPicks = (picks, color, width = 2) => {
            if (!picks?.length) return;
            ctx.strokeStyle = color;
            ctx.lineWidth = width;
            ctx.beginPath();
            picks.forEach((pick, index) => {
                const x = (Number(pick.trace) / Math.max(1, cols - 1)) * w;
                const y = (Number(pick.sample) / Math.max(1, rows - 1)) * h;
                if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            });
            ctx.stroke();
        };
        const sectionMode = section.mode || 'line';
        const sectionValue = section.mode ? Number(section.value) : null;
        const visibleHorizons = (this._segyHorizons || []).filter(horizon => {
            if ((horizon.mode || 'line') !== sectionMode) return false;
            return sectionValue === null || Number(horizon.section_value) === sectionValue;
        });
        for (const horizon of visibleHorizons) drawPicks(horizon.picks, horizon.color || '#f0883e', 2);
        if (!section.mode) {
            for (const fault of this._segyFaults || []) {
                if ((fault.picks || []).length === 1) {
                    const pick = fault.picks[0];
                    const x = (Number(pick.trace) / Math.max(1, cols - 1)) * w;
                    const y = (Number(pick.sample) / Math.max(1, rows - 1)) * h;
                    ctx.strokeStyle = fault.color || '#f85149';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.moveTo(x, Math.max(0, y - 12));
                    ctx.lineTo(x, Math.min(h, y + 12));
                    ctx.stroke();
                } else {
                    drawPicks(fault.picks, fault.color || '#f85149', 2);
                }
            }
        } else {
            this._drawSeismicFaultLinks(ctx, section, w, h, rows);
        }
        drawPicks(this._segyPicks || [], '#ffffff', 1.5);
        this._drawSeismicFaultMap();
    },

    _drawSeismicFaultLinks(ctx, section, w, h, rows) {
        const labels = section.labels || [];
        if (!labels.length) return;
        for (const link of this._segyFaultLinks || []) {
            const points = (link.points || []).filter(point =>
                section.mode === 'inline' ? Number(point.inline) === Number(section.value) : Number(point.crossline) === Number(section.value)
            );
            if (!points.length) continue;
            const ordered = points.slice().sort((a, b) =>
                (section.mode === 'inline' ? a.crossline - b.crossline : a.inline - b.inline)
            );
            ctx.strokeStyle = link.color || '#f85149';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ordered.forEach((point, index) => {
                const other = section.mode === 'inline' ? Number(point.crossline) : Number(point.inline);
                const labelIndex = labels.indexOf(other);
                if (labelIndex < 0) return;
                const x = (labelIndex / Math.max(1, labels.length - 1)) * w;
                const y = (Number(point.sample) / Math.max(1, section.sample_step || 1) / Math.max(1, rows - 1)) * h;
                if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            });
            ctx.stroke();
        }
    },

    _drawSeismicFaultMap() {
        const canvas = document.getElementById('segyFaultMap');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);
        const links = this._segyFaultLinks || [];
        const points = links.flatMap(link => link.points || []);
        if (!points.length) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '13px sans-serif';
            ctx.fillText('No 3D fault links to map', 18, 28);
            return;
        }
        const all = points.concat(...links.map(link => link.polygon || []));
        const inlineValues = all.map(point => Number(point.inline)).filter(Number.isFinite);
        const crosslineValues = all.map(point => Number(point.crossline)).filter(Number.isFinite);
        const inlineMin = Math.min(...inlineValues);
        const inlineMax = Math.max(...inlineValues);
        const crosslineMin = Math.min(...crosslineValues);
        const crosslineMax = Math.max(...crosslineValues);
        const left = 52;
        const right = w - 18;
        const top = 18;
        const bottom = h - 30;
        const x = value => left + ((value - crosslineMin) / Math.max(1, crosslineMax - crosslineMin)) * (right - left);
        const y = value => bottom - ((value - inlineMin) / Math.max(1, inlineMax - inlineMin)) * (bottom - top);
        ctx.strokeStyle = '#21262d';
        ctx.fillStyle = '#8b949e';
        ctx.font = '11px sans-serif';
        ctx.lineWidth = 1;
        for (let index = 0; index <= 4; index += 1) {
            const gx = left + (index / 4) * (right - left);
            const gy = bottom - (index / 4) * (bottom - top);
            ctx.beginPath();
            ctx.moveTo(gx, top);
            ctx.lineTo(gx, bottom);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(left, gy);
            ctx.lineTo(right, gy);
            ctx.stroke();
            ctx.fillText(String(Math.round(crosslineMin + (index / 4) * (crosslineMax - crosslineMin))), gx - 10, h - 10);
            ctx.fillText(String(Math.round(inlineMin + (index / 4) * (inlineMax - inlineMin))), 6, gy + 4);
        }
        ctx.fillText('crossline', right - 54, h - 10);
        ctx.save();
        ctx.translate(12, top + 34);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('inline', 0, 0);
        ctx.restore();
        for (const link of links) {
            const color = link.color || '#f85149';
            const polygon = link.polygon || [];
            if (polygon.length >= 3) {
                ctx.beginPath();
                polygon.forEach((point, index) => {
                    const px = x(Number(point.crossline));
                    const py = y(Number(point.inline));
                    if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
                });
                ctx.closePath();
                ctx.fillStyle = 'rgba(248, 81, 73, 0.16)';
                ctx.fill();
                ctx.strokeStyle = color;
                ctx.lineWidth = 1;
                ctx.stroke();
            }
            const ordered = (link.points || []).slice().sort((a, b) =>
                Number(a.inline) - Number(b.inline) || Number(a.crossline) - Number(b.crossline)
            );
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ordered.forEach((point, index) => {
                const px = x(Number(point.crossline));
                const py = y(Number(point.inline));
                if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
            });
            ctx.stroke();
        }
    },

    _onSegyClick(event) {
        const canvas = document.getElementById('segyCanvas');
        const section = this._segySection;
        if (!canvas || !section?.data?.length) return;
        const rect = canvas.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width;
        const y = (event.clientY - rect.top) / rect.height;
        const rows = section.data.length;
        const cols = section.data[0].length;
        const trace = Math.max(0, Math.min(cols - 1, Math.round(x * (cols - 1))));
        const sample = Math.max(0, Math.min(rows - 1, Math.round(y * (rows - 1))));
        if (!this._segyPicks) this._segyPicks = [];
        this._segyPicks.push({ trace, sample });
        this._segyPicks.sort((a, b) => a.trace - b.trace);
        this._drawSeismic();
        const status = document.getElementById('segyStatus');
        if (status) status.textContent = `${this._segyPicks.length} picks`;
    },

    async saveSeismicHorizon() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        const picks = this._segyPicks || [];
        if (!picks.length) return GeoToast.warn('Click the section to add picks first.');
        const name = document.getElementById('segyHorizonName')?.value || 'Horizon';
        const color = document.getElementById('segyHorizonColor')?.value || '#f0883e';
        const section = this._segySection || {};
        const mode = section.mode || 'line';
        const sectionValue = section.mode ? Number(section.value) : null;
        try {
            await this._api(`/seismic/${line.id}/horizons`, {
                method: 'POST',
                body: JSON.stringify({ name, color, mode, section_value: sectionValue, picks }),
            });
            GeoToast.success(`Horizon saved${section.mode ? ` on ${mode} ${sectionValue}` : ''}`);
            await this._reloadSeismicSection();
        } catch (e) {
            GeoToast.error('Horizon save failed: ' + e.message);
        }
    },

    async _reloadSeismicSection() {
        const section = this._segySection;
        if (section?.mode) {
            await this.loadSeismicVolumeSection(section.mode, section.value);
        } else if (this._segyLine) {
            await this.loadSeismicLine(this._segyLine.id);
        }
    },

    _renderSeismicHorizonList() {
        const host = document.getElementById('segyHorizonList');
        if (!host) return;
        const rows = this._segyHorizons || [];
        const faults = this._segyFaults || [];
        const horizonsHtml = rows.length
            ? rows.map(h => {
                const sectionLabel = h.mode && h.mode !== 'line' ? ` · ${escapeHtml(h.mode)} ${h.section_value}` : '';
                return `<span style="margin-right:12px"><span style="display:inline-block;width:10px;height:10px;background:${escapeHtml(h.color || '#f0883e')};border-radius:2px"></span> ${escapeHtml(h.name)}${sectionLabel} (${(h.picks || []).length})</span>`;
            }).join('')
            : 'No horizons picked yet.';
        const faultsHtml = faults.length
            ? faults.map(f => `<span style="margin-right:12px;color:#f85149">${escapeHtml(f.name)} · ${(f.picks || []).length} pts</span>`).join('')
            : 'No faults detected.';
        const links = this._segyFaultLinks || [];
        const linksHtml = links.length
            ? links.map(link => {
                const geometry = link.geometry || {};
                const throwText = geometry.throw_m != null
                    ? ` · throw ±${geometry.throw_m} m`
                    : (geometry.throw_ms != null ? ` · throw ±${geometry.throw_ms} ms TWT` : '');
                const dipText = geometry.dip_angle_deg != null
                    ? ` · dip ${geometry.dip_angle_deg}°`
                    : (geometry.dip_inline_ms_per_line != null ? ` · time dip ${geometry.dip_inline_ms_per_line}/${geometry.dip_crossline_ms_per_line} ms/line` : '');
                return `<span style="margin-right:12px;color:#ff7b72">${escapeHtml(link.name)} · inline ${link.inline_start}-${link.inline_end} · ${(link.points || []).length} pts${throwText}${dipText}</span>`;
            }).join('')
            : 'No 3D fault links.';
        host.innerHTML = `${horizonsHtml}<div style="margin-top:4px">${faultsHtml}</div><div style="margin-top:4px">${linksHtml}</div>`;
    },

    async autoTrackSeismic() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        const seed = (this._segyPicks || [])[0];
        const section = this._segySection || {};
        const mode = section.mode || 'line';
        const sectionValue = section.mode ? Number(section.value) : null;
        const name = document.getElementById('segyHorizonName')?.value || 'Auto horizon';
        try {
            const result = await this._api(`/seismic/${line.id}/horizons/auto-track`, {
                method: 'POST',
                body: JSON.stringify({
                    name: `${name} auto`,
                    mode,
                    section_value: sectionValue,
                    seed_trace: seed?.trace,
                    seed_sample: seed?.sample,
                    window: 8,
                    search_radius: 12,
                }),
            });
            GeoToast.success(`Auto-tracked ${result.picks_count} traces (${Math.round(result.confidence * 100)}%)`);
            await this._reloadSeismicSection();
        } catch (e) {
            GeoToast.error('Auto-track failed: ' + e.message);
        }
    },

    async detectSeismicFaults() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        GeoLoading.show('Detecting faults...');
        try {
            const result = await this._api(`/seismic/${line.id}/faults/detect`, {
                method: 'POST',
                body: JSON.stringify({ threshold: 0.35, min_points: 4, max_faults: 20 }),
            });
            GeoToast.success(result.faults?.length ? `${result.faults.length} fault candidate(s)` : 'No faults found');
            await this.loadSeismicLine(line.id);
        } catch (e) {
            GeoToast.error('Fault detection failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },
});
