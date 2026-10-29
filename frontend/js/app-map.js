/**
 * Project map workspace: wells, seismic ties, faults, surfaces and prospects.
 */
Object.assign(GeoLogApp.prototype, {
    async renderWellMap() {
        const projectId = this.currentWell?.project_id || this.projects?.[0]?.id;
        if (!projectId) {
            GeoToast.warn('Select a project first.');
            return;
        }
        const canvas = document.getElementById('mapCanvas');
        try {
            const map = await this._api(`/projects/${projectId}/map`);
            this._projectMap = map;
            this._populateMapLines(map.lines || []);
            this._drawProjectMap();
        } catch (e) {
            GeoToast.error('Map failed: ' + e.message);
            if (canvas) {
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#0d1117';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#8b949e';
                ctx.font = '13px sans-serif';
                ctx.fillText('Map could not be loaded', 18, 30);
            }
        }
    },

    _populateMapLines(lines) {
        const select = document.getElementById('mapLineSelect');
        if (!select) return;
        select.innerHTML = lines.map(line =>
            `<option value="${line.id}">${escapeHtml(line.name || `Line ${line.id}`)}</option>`
        ).join('');
    },

    _drawProjectMap() {
        const canvas = document.getElementById('mapCanvas');
        const map = this._projectMap;
        if (!canvas || !map) return;
        const ctx = canvas.getContext('2d');
        const width = canvas.width;
        const height = canvas.height;
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, width, height);
        const mode = document.getElementById('mapMode')?.value || 'wells';
        this._mapHits = [];
        if (mode === 'seismic') {
            this._drawSeismicMap(ctx, width, height, map);
        } else {
            this._drawWellMap(ctx, width, height, map);
        }
        canvas.onclick = event => this._handleMapClick(event);
    },

    _drawWellMap(ctx, width, height, map) {
        const wells = (map.wells || []).filter(well => Number.isFinite(well.latitude) && Number.isFinite(well.longitude));
        if (!wells.length) {
            this._mapMessage(ctx, 'No wells have latitude/longitude. Add coordinates or use Seismic map.');
            return;
        }
        const pad = { left: 54, right: 20, top: 24, bottom: 38 };
        const plotW = width - pad.left - pad.right;
        const plotH = height - pad.top - pad.bottom;
        const minLon = Math.min(...wells.map(well => well.longitude));
        const maxLon = Math.max(...wells.map(well => well.longitude));
        const minLat = Math.min(...wells.map(well => well.latitude));
        const maxLat = Math.max(...wells.map(well => well.latitude));
        const x = value => pad.left + ((value - minLon) / Math.max(1e-9, maxLon - minLon)) * plotW;
        const y = value => pad.top + (1 - (value - minLat) / Math.max(1e-9, maxLat - minLat)) * plotH;
        this._drawMapFrame(ctx, width, height, pad, 'longitude', 'latitude', minLon, maxLon, minLat, maxLat);
        for (const well of wells) {
            const px = x(well.longitude);
            const py = y(well.latitude);
            ctx.fillStyle = well.id === this.currentWell?.id ? '#f0883e' : '#58a6ff';
            ctx.beginPath();
            ctx.arc(px, py, 6, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#c9d1d9';
            ctx.font = '11px sans-serif';
            ctx.fillText(well.name, px + 9, py + 4);
            this._mapHits.push({ x: px, y: py, wellId: well.id, label: well.name });
        }
        const results = document.getElementById('mapResults');
        if (results) results.textContent = `${wells.length} wells with coordinates`;
    },

    _drawSeismicMap(ctx, width, height, map) {
        const lineId = Number(document.getElementById('mapLineSelect')?.value) || map.lines?.[0]?.id;
        const line = (map.lines || []).find(item => item.id === lineId);
        if (!line) {
            this._mapMessage(ctx, 'Upload a SEG-Y line to use the seismic map.');
            return;
        }
        const ties = (map.ties || []).filter(item => item.line_id === lineId);
        const faults = (map.faults || []).filter(item => item.line_id === lineId);
        const surfaces = (map.surfaces || []).filter(item => item.line_id === lineId);
        const prospects = (map.prospects || []).filter(item => surfaces.some(surface => surface.id === item.surface_id));
        const inlineValues = [line.inline_min, line.inline_max, ...ties.map(item => item.inline)].filter(Number.isFinite);
        const crosslineValues = [line.crossline_min, line.crossline_max, ...ties.map(item => item.crossline)].filter(Number.isFinite);
        for (const fault of faults) {
            for (const point of fault.points || []) {
                inlineValues.push(Number(point.inline));
                crosslineValues.push(Number(point.crossline));
            }
        }
        for (const surface of surfaces) {
            if (Number.isFinite(surface.inline_center)) inlineValues.push(surface.inline_center);
            if (Number.isFinite(surface.crossline_center)) crosslineValues.push(surface.crossline_center);
        }
        const minInline = Math.min(...inlineValues);
        const maxInline = Math.max(...inlineValues);
        const minCrossline = Math.min(...crosslineValues);
        const maxCrossline = Math.max(...crosslineValues);
        const pad = { left: 54, right: 20, top: 24, bottom: 38 };
        const plotW = width - pad.left - pad.right;
        const plotH = height - pad.top - pad.bottom;
        const x = value => pad.left + ((value - minCrossline) / Math.max(1e-9, maxCrossline - minCrossline)) * plotW;
        const y = value => pad.top + (1 - (value - minInline) / Math.max(1e-9, maxInline - minInline)) * plotH;
        this._drawMapFrame(ctx, width, height, pad, 'crossline', 'inline', minCrossline, maxCrossline, minInline, maxInline);
        for (const fault of faults) {
            const polygon = fault.polygon || [];
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
                ctx.strokeStyle = fault.color || '#f85149';
                ctx.lineWidth = 1;
                ctx.stroke();
            }
            const ordered = (fault.points || []).slice().sort((a, b) => Number(a.inline) - Number(b.inline));
            ctx.strokeStyle = fault.color || '#f85149';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ordered.forEach((point, index) => {
                const px = x(Number(point.crossline));
                const py = y(Number(point.inline));
                if (index === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
            });
            ctx.stroke();
        }
        for (const surface of surfaces) {
            if (!Number.isFinite(surface.inline_center) || !Number.isFinite(surface.crossline_center)) continue;
            const px = x(surface.crossline_center);
            const py = y(surface.inline_center);
            ctx.strokeStyle = '#d2a8ff';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(px, py, 8, 0, Math.PI * 2);
            ctx.stroke();
            ctx.fillStyle = '#c9d1d9';
            ctx.font = '11px sans-serif';
            ctx.fillText(surface.name, px + 10, py + 4);
        }
        for (const prospect of prospects) {
            const surface = surfaces.find(item => item.id === prospect.surface_id);
            if (!surface) continue;
            const px = x(surface.crossline_center);
            const py = y(surface.inline_center);
            ctx.fillStyle = '#f2cc60';
            ctx.beginPath();
            ctx.moveTo(px, py - 6);
            ctx.lineTo(px + 6, py);
            ctx.lineTo(px, py + 6);
            ctx.lineTo(px - 6, py);
            ctx.closePath();
            ctx.fill();
            ctx.fillStyle = '#c9d1d9';
            ctx.fillText(prospect.name, px + 9, py - 4);
        }
        for (const tie of ties) {
            const px = x(tie.crossline);
            const py = y(tie.inline);
            ctx.fillStyle = '#58a6ff';
            ctx.beginPath();
            ctx.arc(px, py, 6, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#c9d1d9';
            ctx.font = '11px sans-serif';
            ctx.fillText(tie.well_name, px + 9, py + 4);
            this._mapHits.push({ x: px, y: py, wellId: tie.well_id, label: tie.well_name });
        }
        const results = document.getElementById('mapResults');
        if (results) {
            results.textContent = `${ties.length} ties · ${faults.length} fault links · ${surfaces.length} surfaces · ${prospects.length} prospects`;
        }
    },

    _drawMapFrame(ctx, width, height, pad, xLabel, yLabel, minX, maxX, minY, maxY) {
        const plotW = width - pad.left - pad.right;
        const plotH = height - pad.top - pad.bottom;
        ctx.strokeStyle = '#30363d';
        ctx.lineWidth = 1;
        ctx.strokeRect(pad.left, pad.top, plotW, plotH);
        ctx.fillStyle = '#8b949e';
        ctx.font = '11px sans-serif';
        for (let index = 0; index <= 4; index += 1) {
            const gx = pad.left + (index / 4) * plotW;
            const gy = pad.top + (index / 4) * plotH;
            ctx.fillText(String(Math.round(minX + (index / 4) * (maxX - minX))), gx - 10, height - 10);
            ctx.fillText(String(Math.round(minY + (index / 4) * (maxY - minY))), 4, gy + 4);
        }
        ctx.fillText(xLabel, width - 72, height - 10);
        ctx.save();
        ctx.translate(12, pad.top + 34);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(yLabel, 0, 0);
        ctx.restore();
    },

    _mapMessage(ctx, text) {
        ctx.fillStyle = '#8b949e';
        ctx.font = '13px sans-serif';
        ctx.fillText(text, 18, 30);
    },

    _handleMapClick(event) {
        const canvas = document.getElementById('mapCanvas');
        if (!canvas || !this._mapHits?.length) return;
        const rect = canvas.getBoundingClientRect();
        const x = (event.clientX - rect.left) * (canvas.width / rect.width);
        const y = (event.clientY - rect.top) * (canvas.height / rect.height);
        let best = null;
        let bestDistance = 14;
        for (const hit of this._mapHits) {
            const distance = Math.hypot(hit.x - x, hit.y - y);
            if (distance < bestDistance) {
                best = hit;
                bestDistance = distance;
            }
        }
        if (best) this.selectWell(best.wellId);
    },
});
