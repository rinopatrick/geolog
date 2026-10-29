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
        if (select) {
            select.innerHTML = this._segySurfaces.map(surface =>
                `<option value="${surface.id}">${escapeHtml(surface.name)} · ${surface.stats?.point_count || 0} pts</option>`
            ).join('');
        }
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
        GeoLoading.show('Building 3D surface...');
        try {
            const surface = await this._api(`/seismic/${line.id}/surfaces`, {
                method: 'POST',
                body: JSON.stringify({
                    name,
                    horizon_name: horizonName,
                    max_grid: 96,
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
            if (select) {
                select.innerHTML = this._segySurfaces.map(surface =>
                    `<option value="${surface.id}">${escapeHtml(surface.name)} · ${surface.stats?.point_count || 0} pts</option>`
                ).join('');
                if (selectId) select.value = String(selectId);
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
                const throwText = geometry.throw_ms != null ? ` · throw ±${geometry.throw_ms} ms` : '';
                const dipText = geometry.dip_angle_deg != null
                    ? ` · dip ${geometry.dip_angle_deg}°`
                    : (geometry.dip_inline_ms_per_line != null ? ` · dip ${geometry.dip_inline_ms_per_line}/${geometry.dip_crossline_ms_per_line} ms/line` : '');
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
