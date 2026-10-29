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
            const [payload, horizons] = await Promise.all([
                this._api(`/seismic/${id}/section?max_traces=600&max_samples=600`),
                this._api(`/seismic/${id}/horizons`),
            ]);
            this._segySection = payload.section;
            this._segyLine = payload.line;
            this._segyHorizons = horizons || [];
            this._segyPicks = [];
            this._drawSeismic();
            this._renderSeismicHorizonList();
            const status = document.getElementById('segyStatus');
            if (status) {
                status.textContent = `${payload.section.original_trace_count} traces · ${payload.section.original_sample_count} samples · ${payload.line.sample_interval_ms} ms`;
            }
        } catch (e) {
            GeoToast.error('Seismic section failed: ' + e.message);
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
        for (const horizon of this._segyHorizons || []) drawPicks(horizon.picks, horizon.color || '#f0883e', 2);
        drawPicks(this._segyPicks || [], '#ffffff', 1.5);
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
        host.innerHTML = rows.length
            ? rows.map(h => `<span style="margin-right:12px"><span style="display:inline-block;width:10px;height:10px;background:${escapeHtml(h.color || '#f0883e')};border-radius:2px"></span> ${escapeHtml(h.name)} (${(h.picks || []).length})</span>`).join('')
            : 'No horizons picked yet.';
    },
});
