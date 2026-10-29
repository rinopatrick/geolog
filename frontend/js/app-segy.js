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
            const [payload, horizons, faults, volume, links] = await Promise.all([
                this._api(`/seismic/${id}/section?max_traces=600&max_samples=600`),
                this._api(`/seismic/${id}/horizons`),
                this._api(`/seismic/${id}/faults`),
                this._api(`/seismic/${id}/volume`),
                this._api(`/seismic/${id}/fault-links`),
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
            const status = document.getElementById('segyStatus');
            if (status) {
                const dimensions = volume?.is_3d ? ` · 3D ${volume.inline_count}×${volume.crossline_count}` : '';
                status.textContent = `${payload.section.original_trace_count} traces · ${payload.section.original_sample_count} samples · ${payload.line.sample_interval_ms} ms${dimensions}`;
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
            const payload = await this._api(`/seismic/${line.id}/${mode}/${value}/section?max_traces=600&max_samples=600`);
            this._segySection = payload.section;
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
        try {
            const result = await this._api(`/seismic/${line.id}/faults/link-3d`, {
                method: 'POST',
                body: JSON.stringify({
                    threshold: 0.35,
                    min_points: 4,
                    max_sections: 12,
                    crossline_tolerance: 3,
                    sample_tolerance: 16,
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
        if (!section.mode) {
            for (const horizon of this._segyHorizons || []) drawPicks(horizon.picks, horizon.color || '#f0883e', 2);
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

    _onSegyClick(event) {
        const canvas = document.getElementById('segyCanvas');
        const section = this._segySection;
        if (!canvas || !section?.data?.length) return;
        if (section.mode) {
            GeoToast.warn('Picking is available on the 2D line section; inline/crossline picking is not stored yet.');
            return;
        }
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
        try {
            await this._api(`/seismic/${line.id}/horizons`, {
                method: 'POST',
                body: JSON.stringify({ name, color, picks }),
            });
            GeoToast.success('Horizon saved');
            await this.loadSeismicLine(line.id);
        } catch (e) {
            GeoToast.error('Horizon save failed: ' + e.message);
        }
    },

    _renderSeismicHorizonList() {
        const host = document.getElementById('segyHorizonList');
        if (!host) return;
        const rows = this._segyHorizons || [];
        const faults = this._segyFaults || [];
        const horizonsHtml = rows.length
            ? rows.map(h => `<span style="margin-right:12px"><span style="display:inline-block;width:10px;height:10px;background:${escapeHtml(h.color || '#f0883e')};border-radius:2px"></span> ${escapeHtml(h.name)} (${(h.picks || []).length})</span>`).join('')
            : 'No horizons picked yet.';
        const faultsHtml = faults.length
            ? faults.map(f => `<span style="margin-right:12px;color:#f85149">${escapeHtml(f.name)} · ${(f.picks || []).length} pts</span>`).join('')
            : 'No faults detected.';
        const links = this._segyFaultLinks || [];
        const linksHtml = links.length
            ? links.map(link => `<span style="margin-right:12px;color:#ff7b72">${escapeHtml(link.name)} · inline ${link.inline_start}-${link.inline_end} · ${(link.points || []).length} pts</span>`).join('')
            : 'No 3D fault links.';
        host.innerHTML = `${horizonsHtml}<div style="margin-top:4px">${faultsHtml}</div><div style="margin-top:4px">${linksHtml}</div>`;
    },

    async autoTrackSeismic() {
        const line = this._segyLine;
        if (!line) return GeoToast.warn('Load a SEG-Y line first.');
        const seed = (this._segyPicks || [])[0];
        const name = document.getElementById('segyHorizonName')?.value || 'Auto horizon';
        try {
            const result = await this._api(`/seismic/${line.id}/horizons/auto-track`, {
                method: 'POST',
                body: JSON.stringify({
                    name: `${name} auto`,
                    seed_trace: seed?.trace,
                    seed_sample: seed?.sample,
                    window: 8,
                    search_radius: 12,
                }),
            });
            GeoToast.success(`Auto-tracked ${result.picks_count} traces (${Math.round(result.confidence * 100)}%)`);
            await this.loadSeismicLine(line.id);
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
