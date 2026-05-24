/**
 * GeoLog — Professional Multi-Track Well Log Canvas Renderer
 * Oil & Gas industry standard display with depth ruler, hover readout,
 * track configuration, zone picking, and lithology column.
 */
class LogRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.dpr = window.devicePixelRatio || 1;

        // Display config
        this.tracks = [
            { name: 'GR / SP / CAL', curves: ['GR', 'SGR', 'CGR', 'SP', 'CAL', 'CALI', 'HCAL', 'BS'], width: 180 },
            { name: 'Resistivity', curves: ['RT', 'RESD', 'RXO', 'RILD', 'RILM', 'RLL3', 'RLLS', 'ILD', 'ILM', 'MSFL'], width: 180, log: true },
            { name: 'Porosity', curves: ['NPHI', 'NPHI_LS', 'RHOB', 'RHOZ', 'DT', 'DTC', 'DTS', 'PEF', 'DRHO'], width: 180 },
            { name: 'Saturation', curves: ['SW', 'VSH', 'PHIE', 'PHIT', 'BVW', 'PERM'], width: 180 },
        ];

        // Layout constants
        this.depthTrackWidth = 70;       // Depth ruler column
        this.lithTrackWidth = 50;        // Lithology column
        this.headerHeight = 55;          // Track header area
        this.depthLabelHeight = 20;      // Depth label row
        this.margin = { top: 80, bottom: 40, left: 10, right: 10 };

        // Data
        this.depthData = [];
        this.curveData = {};
        this.formationTops = [];
        this.zones = [];              // Picked zones [{name, top, bottom, color}]
        this.dstIntervals = [];
        this.rftPoints = [];
        this.badHoleIntervals = [];
        this.completionData = [];
        this.showCompletionTrack = true;
        this.completionTrackWidth = 72;

        // View state
        this.viewStart = 5000;
        this.viewStop = 5060;
        this.scale = 100;  // ft/in
        this.pixelsPerFoot = 10;  // calculated

        // Hover state
        this.mouseY = -1;
        this.mouseX = -1;
        this.hoverDepth = -1;

        // Curve config (from backend)
        this.curveConfig = {};
        this.lithologyData = null;

        // Manual edit overlay state
        this.editOverlay = {
            enabled: false,
            mnemonic: null,
            selected: [],
            edited: [],
            ghosts: [],
        };

        // Run overlay state (same-track run comparison)
        this.overlayData = null;

        // Colors
        this.colors = {
            bg: '#0d1117',
            trackBg: '#161b22',
            trackBorder: '#30363d',
            headerBg: '#1c2128',
            headerText: '#8b949e',
            depthText: '#c9d1d9',
            gridLine: '#21262d',
            gridLineLight: '#1a1f25',
            formationTop: '#f0883e',
            cursorLine: '#58a6ff',
            tooltipBg: 'rgba(13,17,23,0.92)',
            tooltipBorder: '#30363d',
            tooltipText: '#c9d1d9',
            zoneColors: ['#1f6feb', '#238636', '#8957e5', '#da3633', '#d29922', '#f0883e'],
        };

        this._setupCanvas();
        this._bindEvents();
    }

    _setupCanvas() {
        const container = this.canvas.parentElement;
        if (!container) return;
        const rect = container.getBoundingClientRect();
        this.canvas.width = rect.width * this.dpr;
        this.canvas.height = rect.height * this.dpr;
        this.canvas.style.width = rect.width + 'px';
        this.canvas.style.height = rect.height + 'px';
        this.ctx.scale(this.dpr, this.dpr);
        this.width = rect.width;
        this.height = rect.height;
    }

    _bindEvents() {
        this.canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
        this.canvas.addEventListener('mouseleave', () => this._onMouseLeave());
        this.canvas.addEventListener('wheel', (e) => this._onWheel(e), { passive: false });
        this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
        this.canvas.addEventListener('mouseup', (e) => this._onMouseUp(e));

        window.addEventListener('resize', () => {
            this._setupCanvas();
            this.render();
        });
    }

    // ─── Data ───────────────────────────────────────────────
    setData(depthData, curveData, formationTops, curveConfig) {
        this.depthData = depthData;
        this.curveData = curveData;
        this.formationTops = formationTops || [];
        this.curveConfig = curveConfig || {};
        this._autoFitView();
        this.render();
    }

    setLithologyData(lithologyData) {
        this.lithologyData = lithologyData || null;
        this.render();
    }

    setZones(zones) {
        this.zones = zones || [];
        this.render();
    }

    setBadHoleIntervals(intervals) {
        this.badHoleIntervals = Array.isArray(intervals) ? intervals : [];
        this.render();
    }

    setCompletionData(components) {
        this.completionData = Array.isArray(components) ? components : [];
        this.render();
    }

    setCompletionTrackVisible(visible) {
        this.showCompletionTrack = !!visible;
        this.render();
    }

    updateTracks(tracks) {
        this.tracks = tracks;
        this.render();
    }

    _autoFitView() {
        if (this.depthData.length > 0) {
            this.viewStart = this.depthData[0];
            this.viewStop = this.depthData[this.depthData.length - 1];
            // Default show ~200ft window or full range
            const range = this.viewStop - this.viewStart;
            if (range > 200) {
                this.viewStop = this.viewStart + 200;
            }
        }
    }

    setView(start, stop) {
        this.viewStart = start;
        this.viewStop = stop;
        this.requestRender();
        if (typeof this.onViewChanged === 'function') this.onViewChanged(this.viewStart, this.viewStop);
    }

    setScale(scale) {
        this.scale = scale;
        this.pixelsPerFoot = (this.height - this.margin.top - this.margin.bottom) / scale;
        this.requestRender();
    }

    // ─── Mouse Events ───────────────────────────────────────
    _onMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        this.mouseX = e.clientX - rect.left;
        this.mouseY = e.clientY - rect.top;
        this.hoverDepth = this._yToDepth(this.mouseY);
        this.requestRender();
        this._showTooltip(e);
    }

    _onMouseLeave() {
        this.mouseY = -1;
        this.mouseX = -1;
        this.hoverDepth = -1;
        this.requestRender();
        this._hideTooltip();
    }

    _onWheel(e) {
        e.preventDefault();
        const range = this.viewStop - this.viewStart;
        const delta = e.deltaY > 0 ? range * 0.1 : -range * 0.1;
        const newStart = this.viewStart + delta;
        const newStop = this.viewStop + delta;
        if (newStart >= this.depthData[0] && newStop <= this.depthData[this.depthData.length - 1]) {
            this.viewStart = newStart;
            this.viewStop = newStop;
            this.requestRender();
            this._updateDepthInputs();
            if (typeof this.onViewChanged === 'function') this.onViewChanged(this.viewStart, this.viewStop);
        }
    }

    _dragStart = null;
    _onMouseDown(e) {
        this._dragStart = { y: e.clientY, viewStart: this.viewStart, viewStop: this.viewStop };
    }

    _onMouseUp(e) {
        if (this._dragStart) {
            const dy = e.clientY - this._dragStart.y;
            const feetPerPixel = (this._dragStart.viewStop - this._dragStart.viewStart) / (this.height - this.margin.top - this.margin.bottom);
            const depthDelta = -dy * feetPerPixel;
            const range = this._dragStart.viewStop - this._dragStart.viewStart;
            this.viewStart = this._dragStart.viewStart + depthDelta;
            this.viewStop = this.viewStart + range;
            // Clamp
            const dataStart = this.depthData[0];
            const dataEnd = this.depthData[this.depthData.length - 1];
            if (this.viewStart < dataStart) { this.viewStart = dataStart; this.viewStop = dataStart + range; }
            if (this.viewStop > dataEnd) { this.viewStop = dataEnd; this.viewStart = dataEnd - range; }
            this._dragStart = null;
            this.requestRender();
            this._updateDepthInputs();
            if (typeof this.onViewChanged === 'function') this.onViewChanged(this.viewStart, this.viewStop);
        }
    }

    _yToDepth(y) {
        const plotTop = this.margin.top;
        const plotBottom = this.height - this.margin.bottom;
        const plotHeight = plotBottom - plotTop;
        if (y < plotTop || y > plotBottom) return -1;
        return this.viewStart + ((y - plotTop) / plotHeight) * (this.viewStop - this.viewStart);
    }

    _depthToY(depth) {
        const plotTop = this.margin.top;
        const plotBottom = this.height - this.margin.bottom;
        const plotHeight = plotBottom - plotTop;
        return plotTop + ((depth - this.viewStart) / (this.viewStop - this.viewStart)) * plotHeight;
    }

    _updateDepthInputs() {
        const topInput = document.getElementById('depthTop');
        const bottomInput = document.getElementById('depthBottom');
        if (topInput) topInput.value = this.viewStart.toFixed(1);
        if (bottomInput) bottomInput.value = this.viewStop.toFixed(1);
    }

    // ─── Tooltip ────────────────────────────────────────────
    _showTooltip(e) {
        if (this.hoverDepth < 0) { this._hideTooltip(); return; }
        let tooltip = document.getElementById('log-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'log-tooltip';
            document.body.appendChild(tooltip);
        }

        const depth = this.hoverDepth;
        // Find nearest depth index
        let idx = 0;
        let minDist = Infinity;
        for (let i = 0; i < this.depthData.length; i++) {
            const d = Math.abs(this.depthData[i] - depth);
            if (d < minDist) { minDist = d; idx = i; }
        }

        let html = `<div class="tt-depth">${this.depthData[idx]?.toFixed(2)} ${this._depthUnit()}</div>`;
        for (const track of this.tracks) {
            for (const mnemonic of track.curves) {
                if (this.curveData[mnemonic] && this.curveData[mnemonic][idx] !== null && this.curveData[mnemonic][idx] !== undefined) {
                    const cfg = this.curveConfig[mnemonic] || {};
                    const color = cfg.color || '#8b949e';
                    const val = this.curveData[mnemonic][idx];
                    const unit = cfg.unit || '';
                    html += `<div class="tt-row"><span class="tt-dot" style="background:${color}"></span><span class="tt-mnem">${mnemonic}</span><span class="tt-val">${val.toFixed(4)}</span><span class="tt-unit">${unit}</span></div>`;
                }
            }
        }

        tooltip.innerHTML = html;
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 15) + 'px';
        tooltip.style.top = (e.clientY - 10) + 'px';
        // Keep tooltip in viewport
        const rect = tooltip.getBoundingClientRect();
        if (rect.right > window.innerWidth) {
            tooltip.style.left = (e.clientX - rect.width - 15) + 'px';
        }
        if (rect.bottom > window.innerHeight) {
            tooltip.style.top = (e.clientY - rect.height - 10) + 'px';
        }
    }

    _hideTooltip() {
        const tooltip = document.getElementById('log-tooltip');
        if (tooltip) tooltip.style.display = 'none';
    }

    _depthUnit() {
        const wells = document.getElementById('depthUnit');
        return wells?.textContent || 'FT';
    }

    requestRender() {
        if (this._rafPending) return;
        this._rafPending = true;
        requestAnimationFrame(() => {
            this._rafPending = false;
            this.render();
        });
    }

    _computeRenderStride(visibleCount) {
        if (!Number.isFinite(visibleCount) || visibleCount <= 0) return 1;
        const targetSamples = Math.max(300, Math.floor((this.height - this.margin.top - this.margin.bottom) * 1.2));
        return Math.max(1, Math.ceil(visibleCount / targetSamples));
    }

    // ─── Rendering ──────────────────────────────────────────
    render() {
        const ctx = this.ctx;
        const w = this.width;
        const h = this.height;

        // Clear
        ctx.fillStyle = this.colors.bg;
        ctx.fillRect(0, 0, w, h);

        // Calculate layout
        const totalTrackWidth = this.tracks.reduce((s, t) => s + t.width, 0);
        const completionTrackWidth = this.showCompletionTrack ? this.completionTrackWidth : 0;
        const totalPlotWidth = totalTrackWidth + completionTrackWidth;
        const lithTrackWidth = (this._showLithology && this.lithologyData?.lith_code?.length) ? 46 : 0;
        const startX = this.margin.left + this.depthTrackWidth + lithTrackWidth;
        const plotTop = this.margin.top;
        const plotBottom = h - this.margin.bottom;
        const plotHeight = plotBottom - plotTop;

        // Draw formation tops (background)
        this._drawFormationTops(ctx, startX, totalPlotWidth, plotTop, plotBottom);

        // Draw DST intervals (background)
        this._drawDSTIntervals(ctx, startX, totalPlotWidth, plotTop, plotBottom);

        // Draw zones (background)
        this._drawZones(ctx, startX, totalPlotWidth, plotTop, plotBottom);

        // Draw bad-hole intervals (LQC overlay)
        this._drawBadHoleIntervals(ctx, startX, totalPlotWidth, plotTop, plotBottom);

        // Draw lithology track (if enabled)
        if (lithTrackWidth > 0) {
            this._drawLithTrack(ctx, startX - lithTrackWidth, lithTrackWidth, plotTop, plotBottom);
        }

        // Draw depth ruler
        this._drawDepthRuler(ctx, this.margin.left, this.depthTrackWidth, plotTop, plotBottom);

        // Draw formation column in depth track area
        this._drawFormationColumn(ctx, this.margin.left, this.depthTrackWidth, plotTop, plotBottom);

        // Draw tracks
        let trackX = startX;
        for (let t = 0; t < this.tracks.length; t++) {
            const track = this.tracks[t];
            this._drawTrack(ctx, track, t, trackX, plotTop, plotBottom, track.width);
            trackX += track.width;
        }

        if (completionTrackWidth > 0) {
            this._drawCompletionTrack(ctx, trackX, plotTop, plotBottom, completionTrackWidth);
        }

        // Manual edit overlay
        this._drawEditOverlay(ctx);

        // Draw header
        this._drawHeaders(ctx, startX, totalTrackWidth, completionTrackWidth);

        // Draw cursor line
        if (this.mouseY > plotTop && this.mouseY < plotBottom) {
            ctx.strokeStyle = this.colors.cursorLine;
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(this.margin.left, this.mouseY);
            ctx.lineTo(w - this.margin.right, this.mouseY);
            ctx.stroke();
            ctx.setLineDash([]);

            // Depth readout at cursor
            if (this.hoverDepth > 0) {
                ctx.fillStyle = this.colors.cursorLine;
                ctx.font = 'bold 11px IBM Plex Mono';
                ctx.textAlign = 'right';
                ctx.fillText(this.hoverDepth.toFixed(1), this.margin.left + this.depthTrackWidth - 5, this.mouseY - 4);
            }
        }

        // Draw formation top labels
        this._drawFormationTopLabels(ctx, startX, totalPlotWidth, plotTop, plotBottom);

        // Draw RFT points (foreground)
        this._drawRFTPoints(ctx, startX, totalPlotWidth, plotTop, plotBottom);
    }

    setEditOverlay(overlay = {}) {
        this.editOverlay = {
            enabled: !!overlay.enabled,
            mnemonic: overlay.mnemonic || null,
            selected: Array.isArray(overlay.selected) ? overlay.selected : [],
            edited: Array.isArray(overlay.edited) ? overlay.edited : [],
            ghosts: Array.isArray(overlay.ghosts) ? overlay.ghosts : [],
        };
        this.render();
    }

    setOverlayData(overlay = null) {
        this.overlayData = overlay;
        this.requestRender();
    }

    _drawEditOverlay(ctx) {
        if (!this.editOverlay?.enabled) return;
        const drawPts = (pts, fill, radius = 3.5, stroke = null) => {
            for (const p of pts) {
                if (!Number.isFinite(p?.x) || !Number.isFinite(p?.y)) continue;
                ctx.beginPath();
                ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
                ctx.fillStyle = fill;
                ctx.fill();
                if (stroke) {
                    ctx.strokeStyle = stroke;
                    ctx.lineWidth = 1;
                    ctx.stroke();
                }
            }
        };
        drawPts(this.editOverlay.ghosts, 'rgba(148,163,184,0.45)', 3.2, 'rgba(100,116,139,0.8)');
        drawPts(this.editOverlay.edited, '#f97316', 4.2, '#fb923c');
        drawPts(this.editOverlay.selected, '#fde047', 4.8, '#facc15');
    }

    _valueToXInTrack(val, scale, useLog, trackX, width) {
        let x;
        if (useLog) {
            const logMin = Math.log10(Math.max(scale[0], 0.001));
            const logMax = Math.log10(Math.max(scale[1], 0.001));
            const logVal = Math.log10(Math.max(val, 0.001));
            const normalized = (logVal - logMin) / (logMax - logMin);
            x = trackX + width - normalized * width;
        } else {
            let normalized;
            if (scale[0] > scale[1]) normalized = (scale[0] - val) / (scale[0] - scale[1]);
            else normalized = (val - scale[0]) / (scale[1] - scale[0]);
            x = trackX + normalized * width;
        }
        return Math.max(trackX, Math.min(trackX + width, x));
    }

    getCurvePointAtIndex(mnemonic, idx, overrideValue = undefined) {
        if (!this.depthData?.length || !Number.isFinite(idx) || idx < 0 || idx >= this.depthData.length) return null;
        const depth = this.depthData[idx];
        let trackX = this.margin.left + this.depthTrackWidth;
        for (const track of this.tracks) {
            if (!track.curves.includes(mnemonic)) {
                trackX += track.width;
                continue;
            }
            const data = this.curveData[mnemonic];
            if (!data || idx >= data.length) return null;
            const v = overrideValue !== undefined ? overrideValue : data[idx];
            if (v === null || v === undefined || Number.isNaN(v)) return null;
            const cfg = this.curveConfig[mnemonic] || {};
            const scale = cfg.scale || [0, 100];
            const x = this._valueToXInTrack(v, scale, !!track.log, trackX, track.width);
            const y = this._depthToY(depth);
            return { mnemonic, index: idx, depth, value: v, x, y };
        }
        return null;
    }

    getNearestCurvePoint(mouseX, mouseY, preferredMnemonic = null) {
        if (!this.depthData?.length) return null;
        const plotTop = this.margin.top;
        const plotBottom = this.height - this.margin.bottom;
        if (mouseY < plotTop || mouseY > plotBottom) return null;

        const depth = this._yToDepth(mouseY);
        let idx = 0;
        let minDepthDist = Infinity;
        for (let i = 0; i < this.depthData.length; i++) {
            const d = Math.abs(this.depthData[i] - depth);
            if (d < minDepthDist) { minDepthDist = d; idx = i; }
        }

        let best = null;
        const maxPx = 14;
        const candidates = preferredMnemonic
            ? [preferredMnemonic]
            : this.tracks.flatMap(t => t.curves);
        for (const mnemonic of candidates) {
            const p = this.getCurvePointAtIndex(mnemonic, idx);
            if (!p) continue;
            const dist = Math.hypot(mouseX - p.x, mouseY - p.y);
            if (dist <= maxPx && (!best || dist < best.distance)) best = { ...p, distance: dist };
        }
        return best;
    }

    _drawFormationColumn(ctx, x, width, plotTop, plotBottom) {
        const plotHeight = plotBottom - plotTop;

        // Draw empty track if no tops
        if (!this.formationTops || !this.formationTops.length) {
            ctx.save();
            ctx.fillStyle = 'rgba(13,17,23,0.25)';
            ctx.fillRect(x, plotTop, width, plotHeight);
            ctx.strokeStyle = this.colors.trackBorder;
            ctx.strokeRect(x, plotTop, width, plotHeight);
            ctx.restore();
            return;
        }

        const sorted = [...this.formationTops]
            .filter(t => Number.isFinite(Number(t.depth)))
            .sort((a, b) => Number(a.depth) - Number(b.depth));
        if (!sorted.length) return;

        const alphaColor = (hex, alpha = '4d') => {
            if (!hex || typeof hex !== 'string') return null;
            const c = hex.trim();
            if (c.startsWith('#') && c.length === 7) return c + alpha;
            if (c.startsWith('#') && c.length === 4) {
                const r = c[1], g = c[2], b = c[3];
                return `#${r}${r}${g}${g}${b}${b}${alpha}`;
            }
            return null;
        };

        const fallback = ['#ffb74d4d', '#81c7844d', '#90caf94d', '#ce93d84d', '#ff8a804d', '#ffd54f4d', '#4dd0e54d', '#ba68c84d'];

        ctx.save();
        for (let i = 0; i < sorted.length; i++) {
            const top = sorted[i];
            const topY = this._depthToY(Number(top.depth));
            const nextDepth = i + 1 < sorted.length ? Number(sorted[i + 1].depth) : this.viewStop;
            const bottomY = this._depthToY(nextDepth);
            const y1 = Math.max(plotTop, Math.min(topY, bottomY));
            const y2 = Math.min(plotBottom, Math.max(topY, bottomY));
            if (y2 <= y1) continue;

            ctx.fillStyle = alphaColor(top.color, '4d') || fallback[i % fallback.length];
            ctx.fillRect(x, y1, width, y2 - y1);

            const name = top.formation_name || top.name || '';
            if (name && (y2 - y1) > 26) {
                ctx.save();
                ctx.translate(x + width / 2, (y1 + y2) / 2);
                ctx.rotate(-Math.PI / 2);
                ctx.fillStyle = top.color || '#c9d1d9';
                ctx.font = 'bold 9px DM Sans';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(name, 0, 0);
                ctx.restore();
            }
        }

        ctx.strokeStyle = this.colors.trackBorder;
        ctx.lineWidth = 1;
        ctx.strokeRect(x, plotTop, width, plotHeight);
        ctx.restore();
    }

    _drawDepthRuler(ctx, x, width, plotTop, plotBottom) {
        const range = this.viewStop - this.viewStart;
        const plotHeight = plotBottom - plotTop;

        // Background
        ctx.fillStyle = this.colors.trackBg;
        ctx.fillRect(x, plotTop, width, plotHeight);

        // Border right
        ctx.strokeStyle = this.colors.trackBorder;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x + width, plotTop);
        ctx.lineTo(x + width, plotBottom);
        ctx.stroke();

        // Calculate tick interval
        const ftPerPixel = range / plotHeight;
        const totalFeet = range;
        let majorInterval, minorInterval;
        if (totalFeet <= 50) { majorInterval = 5; minorInterval = 1; }
        else if (totalFeet <= 100) { majorInterval = 10; minorInterval = 5; }
        else if (totalFeet <= 300) { majorInterval = 20; minorInterval = 5; }
        else if (totalFeet <= 500) { majorInterval = 50; minorInterval = 10; }
        else { majorInterval = 100; minorInterval = 20; }

        const startTick = Math.ceil(this.viewStart / minorInterval) * minorInterval;

        for (let d = startTick; d <= this.viewStop; d += minorInterval) {
            const y = this._depthToY(d);
            if (y < plotTop || y > plotBottom) continue;

            const isMajor = (d % majorInterval) === 0;

            // Tick mark
            ctx.strokeStyle = this.colors.depthText;
            ctx.lineWidth = isMajor ? 1.5 : 0.5;
            ctx.beginPath();
            if (isMajor) {
                ctx.moveTo(x + 5, y);
                ctx.lineTo(x + width - 5, y);
            } else {
                ctx.moveTo(x + width - 15, y);
                ctx.lineTo(x + width - 5, y);
            }
            ctx.stroke();

            // Label (major only)
            if (isMajor) {
                ctx.fillStyle = this.colors.depthText;
                ctx.font = '10px IBM Plex Mono';
                ctx.textAlign = 'center';
                ctx.fillText(d.toFixed(0), x + width / 2, y + 3.5);
            }
        }

        // Header label
        ctx.fillStyle = this.colors.headerText;
        ctx.font = '10px IBM Plex Mono';
        ctx.textAlign = 'center';
        ctx.fillText('DEPTH', x + width / 2, plotTop - 5);
    }

    _drawTrack(ctx, track, trackIndex, x, plotTop, plotBottom, width) {
        const plotHeight = plotBottom - plotTop;
        const useLog = track.log || false;

        // Track background
        ctx.fillStyle = this.colors.trackBg;
        ctx.fillRect(x, plotTop, width, plotHeight);

        // Track border
        ctx.strokeStyle = this.colors.trackBorder;
        ctx.lineWidth = 1;
        ctx.strokeRect(x, plotTop, width, plotHeight);

        // Grid lines
        ctx.strokeStyle = this.colors.gridLine;
        ctx.lineWidth = 0.5;
        const gridLines = 5;
        for (let i = 1; i < gridLines; i++) {
            const gx = x + (width * i / gridLines);
            ctx.beginPath();
            ctx.moveTo(gx, plotTop);
            ctx.lineTo(gx, plotBottom);
            ctx.stroke();
        }

        // Draw curves
        const activeCurves = track.curves.filter(m => this.curveData[m] && this.curveData[m].length > 0);
        for (const mnemonic of activeCurves) {
            this._drawCurve(ctx, mnemonic, x, plotTop, plotBottom, width, useLog);
        }

        // Draw run overlay curve + optional difference shading
        this._drawOverlayForTrack(ctx, track, x, plotTop, plotBottom, width, useLog);
    }

    _drawOverlayForTrack(ctx, track, trackX, plotTop, plotBottom, width, useLog) {
        const overlay = this.overlayData;
        if (!overlay || !overlay.enabled || !overlay.mnemonic || !track.curves.includes(overlay.mnemonic)) return;
        const baseCfg = this.curveConfig[overlay.mnemonic] || {};
        const scale = baseCfg.scale || [0, 100];
        const depth = overlay.depth || [];
        const runA = overlay.runA || [];
        const runB = overlay.runB || [];
        if (!depth.length || !runB.length) return;

        const visible = depth.filter(d => d >= this.viewStart && d <= this.viewStop).length;
        const stride = this._computeRenderStride(visible);
        const alpha = Math.max(0.05, Math.min(1, Number(overlay.opacity ?? 0.5)));
        const color = overlay.color || '#ff3b30';

        if (overlay.showDifference && runA.length === runB.length) {
            for (let i = 0; i < depth.length - 1; i += stride) {
                const i2 = Math.min(i + stride, depth.length - 1);
                const d1 = depth[i], d2 = depth[i2];
                if (d2 < this.viewStart || d1 > this.viewStop) continue;
                const a1 = runA[i], a2 = runA[i2], b1 = runB[i], b2 = runB[i2];
                if (![a1, a2, b1, b2].every(v => Number.isFinite(v))) continue;
                const y1 = this._depthToY(d1);
                const y2 = this._depthToY(d2);
                if ((y1 < plotTop && y2 < plotTop) || (y1 > plotBottom && y2 > plotBottom)) continue;
                const xa1 = this._valueToXInTrack(a1, scale, useLog, trackX, width);
                const xa2 = this._valueToXInTrack(a2, scale, useLog, trackX, width);
                const xb1 = this._valueToXInTrack(b1, scale, useLog, trackX, width);
                const xb2 = this._valueToXInTrack(b2, scale, useLog, trackX, width);
                const avgDiff = ((b1 - a1) + (b2 - a2)) / 2;
                const fill = avgDiff >= 0
                    ? `rgba(34,197,94,${0.28 * alpha})`
                    : `rgba(239,68,68,${0.28 * alpha})`;
                ctx.fillStyle = fill;
                ctx.beginPath();
                ctx.moveTo(xa1, y1);
                ctx.lineTo(xa2, y2);
                ctx.lineTo(xb2, y2);
                ctx.lineTo(xb1, y1);
                ctx.closePath();
                ctx.fill();
            }
        }

        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        let started = false;
        for (let i = 0; i < depth.length; i += stride) {
            const d = depth[i];
            if (d < this.viewStart || d > this.viewStop) continue;
            const v = runB[i];
            if (!Number.isFinite(v)) { started = false; continue; }
            const y = this._depthToY(d);
            const px = this._valueToXInTrack(v, scale, useLog, trackX, width);
            if (!started) {
                ctx.moveTo(px, y);
                started = true;
            } else {
                ctx.lineTo(px, y);
            }
        }
        ctx.stroke();
        ctx.restore();
    }

    _drawCurve(ctx, mnemonic, trackX, plotTop, plotBottom, width, useLog) {
        const cfg = this.curveConfig[mnemonic] || {};
        const color = cfg.color || '#58a6ff';
        const scale = cfg.scale || [0, 100];
        const data = this.curveData[mnemonic];
        if (!data || data.length === 0) return;

        const plotHeight = plotBottom - plotTop;
        const visible = this.depthData.filter(d => d >= this.viewStart && d <= this.viewStop).length;
        const stride = this._computeRenderStride(visible);

        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();

        let started = false;
        for (let i = 0; i < this.depthData.length; i += stride) {
            const depth = this.depthData[i];
            if (depth < this.viewStart || depth > this.viewStop) continue;

            const val = data[i];
            if (val === null || val === undefined || isNaN(val)) {
                started = false;
                continue;
            }

            const y = plotTop + ((depth - this.viewStart) / (this.viewStop - this.viewStart)) * plotHeight;
            if (y < plotTop || y > plotBottom) continue;
            let x;

            if (useLog) {
                const logMin = Math.log10(Math.max(scale[0], 0.001));
                const logMax = Math.log10(Math.max(scale[1], 0.001));
                const logVal = Math.log10(Math.max(val, 0.001));
                const normalized = (logVal - logMin) / (logMax - logMin);
                x = trackX + width - normalized * width;
            } else {
                let normalized;
                if (scale[0] > scale[1]) normalized = (scale[0] - val) / (scale[0] - scale[1]);
                else normalized = (val - scale[0]) / (scale[1] - scale[0]);
                x = trackX + normalized * width;
            }

            x = Math.max(trackX, Math.min(trackX + width, x));
            if (x < trackX || x > trackX + width) continue;

            if (!started) {
                ctx.moveTo(x, y);
                started = true;
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();

        // Scale labels
        ctx.fillStyle = color;
        ctx.font = '9px IBM Plex Mono';
        ctx.textAlign = 'left';
        ctx.fillText(scale[0].toString(), trackX + 2, plotBottom + 12);
        ctx.textAlign = 'right';
        ctx.fillText(scale[1].toString(), trackX + width - 2, plotBottom + 12);
    }

    _drawHeaders(ctx, startX, totalWidth, completionTrackWidth = 0) {
        let trackX = startX;
        for (const track of this.tracks) {
            // Track header background
            ctx.fillStyle = this.colors.headerBg;
            ctx.fillRect(trackX, 0, track.width, this.margin.top - 15);

            // Track border
            ctx.strokeStyle = this.colors.trackBorder;
            ctx.lineWidth = 1;
            ctx.strokeRect(trackX, 0, track.width, this.margin.top - 15);

            // Track name
            ctx.fillStyle = this.colors.headerText;
            ctx.font = 'bold 11px IBM Plex Mono';
            ctx.textAlign = 'center';
            ctx.fillText(track.name, trackX + track.width / 2, 18);

            // Curve names with colors
            const activeCurves = track.curves.filter(m => this.curveData[m] && this.curveData[m].length > 0);
            let cy = 33;
            for (const mnemonic of activeCurves) {
                const cfg = this.curveConfig[mnemonic] || {};
                ctx.fillStyle = cfg.color || '#58a6ff';
                ctx.font = '10px IBM Plex Mono';
                ctx.textAlign = 'center';
                const unit = cfg.unit ? ` (${cfg.unit})` : '';
                ctx.fillText(mnemonic + unit, trackX + track.width / 2, cy);
                cy += 14;
            }

            trackX += track.width;
        }

        if (completionTrackWidth > 0) {
            ctx.fillStyle = this.colors.headerBg;
            ctx.fillRect(trackX, 0, completionTrackWidth, this.margin.top - 15);
            ctx.strokeStyle = this.colors.trackBorder;
            ctx.lineWidth = 1;
            ctx.strokeRect(trackX, 0, completionTrackWidth, this.margin.top - 15);
            ctx.fillStyle = this.colors.headerText;
            ctx.font = 'bold 10px IBM Plex Mono';
            ctx.textAlign = 'center';
            ctx.fillText('Completion', trackX + completionTrackWidth / 2, 18);
        }
    }

    _drawCompletionTrack(ctx, x, plotTop, plotBottom, width) {
        const h = plotBottom - plotTop;
        ctx.fillStyle = '#11161d';
        ctx.fillRect(x, plotTop, width, h);
        ctx.strokeStyle = this.colors.trackBorder;
        ctx.lineWidth = 1;
        ctx.strokeRect(x, plotTop, width, h);

        const items = (this.completionData || []).filter(c => Number.isFinite(Number(c.depth_top)) && Number.isFinite(Number(c.depth_base)));
        for (const c of items) {
            let top = Number(c.depth_top);
            let base = Number(c.depth_base);
            if (base < top) [top, base] = [base, top];
            const y1 = Math.max(plotTop, Math.min(plotBottom, this._depthToY(top)));
            const y2 = Math.max(plotTop, Math.min(plotBottom, this._depthToY(base)));
            if (y2 < plotTop || y1 > plotBottom) continue;
            const t = String(c.component_type || '').toLowerCase();

            if (t === 'cement') {
                ctx.fillStyle = 'rgba(148, 163, 184, 0.45)';
                ctx.fillRect(x + 1, y1, width - 2, Math.max(1, y2 - y1));
                continue;
            }
            if (t === 'casing' || t === 'liner') {
                ctx.strokeStyle = t === 'liner' ? '#f59e0b' : '#60a5fa';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(x + 12, y1);
                ctx.lineTo(x + 12, y2);
                ctx.moveTo(x + width - 12, y1);
                ctx.lineTo(x + width - 12, y2);
                ctx.stroke();
                if (c.size) {
                    ctx.fillStyle = '#c9d1d9';
                    ctx.font = '9px IBM Plex Mono';
                    ctx.textAlign = 'center';
                    ctx.fillText(String(c.size), x + width / 2, Math.min(y2 - 2, y1 + 10));
                }
                continue;
            }
            if (t === 'tubing') {
                ctx.strokeStyle = '#93c5fd';
                ctx.lineWidth = 1.2;
                ctx.beginPath();
                ctx.moveTo(x + width / 2, y1);
                ctx.lineTo(x + width / 2, y2);
                ctx.stroke();
                continue;
            }
            if (t === 'perforation') {
                ctx.strokeStyle = '#ef4444';
                ctx.setLineDash([4, 3]);
                ctx.beginPath();
                ctx.moveTo(x + 8, y1);
                ctx.lineTo(x + 8, y2);
                ctx.moveTo(x + width - 8, y1);
                ctx.lineTo(x + width - 8, y2);
                ctx.stroke();
                ctx.setLineDash([]);
                continue;
            }
            if (t === 'screen') {
                ctx.strokeStyle = '#22c55e';
                ctx.setLineDash([1, 3]);
                ctx.beginPath();
                ctx.moveTo(x + width / 2, y1);
                ctx.lineTo(x + width / 2, y2);
                ctx.stroke();
                ctx.setLineDash([]);
                continue;
            }
            if (t === 'packer' || t === 'valve') {
                ctx.fillStyle = '#111111';
                ctx.fillRect(x + 8, y1, width - 16, Math.max(4, y2 - y1 || 6));
                continue;
            }
            if (t === 'pump') {
                ctx.fillStyle = '#f97316';
                const hh = Math.max(10, y2 - y1 || 10);
                ctx.fillRect(x + 10, y1, width - 20, hh);
                ctx.fillStyle = '#111827';
                ctx.font = 'bold 9px IBM Plex Mono';
                ctx.textAlign = 'center';
                ctx.fillText('P', x + width / 2, y1 + Math.min(hh - 2, 9));
                continue;
            }
        }
    }

    _drawFormationTops(ctx, startX, totalWidth, plotTop, plotBottom) {
        // Draw colored zone fills between consecutive tops
        const sorted = [...this.formationTops].sort((a, b) => a.depth - b.depth);
        const zoneColors = [
            'rgba(255,183,77,0.10)', 'rgba(129,199,132,0.10)', 'rgba(144,202,249,0.10)',
            'rgba(206,147,216,0.10)', 'rgba(255,138,128,0.10)', 'rgba(255,213,79,0.10)',
            'rgba(77,208,225,0.10)', 'rgba(186,104,200,0.10)',
        ];
        for (let i = 0; i < sorted.length; i++) {
            const topY = this._depthToY(sorted[i].depth);
            const bottomY = (i + 1 < sorted.length) ? this._depthToY(sorted[i + 1].depth) : plotBottom;
            const y1 = Math.max(Math.min(topY, plotBottom), plotTop);
            const y2 = Math.max(Math.min(bottomY, plotBottom), plotTop);
            if (y2 > y1) {
                ctx.fillStyle = zoneColors[i % zoneColors.length];
                ctx.fillRect(startX, y1, totalWidth, y2 - y1);
            }
        }

        // Draw top lines
        for (const top of this.formationTops) {
            const y = this._depthToY(top.depth);
            if (y < plotTop || y > plotBottom) continue;

            // Dashed line across all tracks
            ctx.strokeStyle = top.color || this.colors.formationTop;
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 4]);
            ctx.beginPath();
            ctx.moveTo(startX, y);
            ctx.lineTo(startX + totalWidth, y);
            ctx.stroke();
            ctx.setLineDash([]);
        }
    }

    _drawFormationTopLabels(ctx, startX, totalWidth, plotTop, plotBottom) {
        for (const top of this.formationTops) {
            const y = this._depthToY(top.depth);
            if (y < plotTop || y > plotBottom) continue;

            // Label background
            const label = top.formation_name;
            ctx.font = 'bold 10px DM Sans';
            const tw = ctx.measureText(label).width;
            const lx = startX + totalWidth + 5;
            const ly = y - 6;

            ctx.fillStyle = 'rgba(13,17,23,0.85)';
            ctx.fillRect(lx - 2, ly - 10, tw + 8, 14);
            ctx.fillStyle = top.color || this.colors.formationTop;
            ctx.textAlign = 'left';
            ctx.fillText(label, lx + 2, ly);
        }
    }

    _drawZones(ctx, startX, totalWidth, plotTop, plotBottom) {
        for (let i = 0; i < this.zones.length; i++) {
            const zone = this.zones[i];
            const yTop = this._depthToY(zone.top);
            const yBottom = this._depthToY(zone.bottom);
            if (yBottom < plotTop || yTop > plotBottom) continue;

            const color = zone.color || this.colors.zoneColors[i % this.colors.zoneColors.length];
            ctx.fillStyle = color + '18';  // Low opacity fill
            ctx.fillRect(startX, Math.max(yTop, plotTop), totalWidth, Math.min(yBottom, plotBottom) - Math.max(yTop, plotTop));

            // Zone borders
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.setLineDash([3, 3]);
            if (yTop >= plotTop) {
                ctx.beginPath();
                ctx.moveTo(startX, yTop);
                ctx.lineTo(startX + totalWidth, yTop);
                ctx.stroke();
            }
            if (yBottom <= plotBottom) {
                ctx.beginPath();
                ctx.moveTo(startX, yBottom);
                ctx.lineTo(startX + totalWidth, yBottom);
                ctx.stroke();
            }
            ctx.setLineDash([]);

            // Zone label
            ctx.fillStyle = color;
            ctx.font = 'bold 10px DM Sans';
            ctx.textAlign = 'left';
            ctx.fillText(zone.name, startX + 4, Math.max(yTop, plotTop) + 14);
        }
    }

    _drawDSTIntervals(ctx, startX, totalWidth, plotTop, plotBottom) {
        if (!Array.isArray(this.dstIntervals) || !this.dstIntervals.length) return;
        for (const d of this.dstIntervals) {
            const top = Number(d.top_depth);
            const bottom = Number(d.bottom_depth);
            if (!Number.isFinite(top) || !Number.isFinite(bottom) || bottom <= top) continue;
            const yTop = this._depthToY(top);
            const yBottom = this._depthToY(bottom);
            if (yBottom < plotTop || yTop > plotBottom) continue;
            const y1 = Math.max(plotTop, yTop);
            const y2 = Math.min(plotBottom, yBottom);
            ctx.fillStyle = 'rgba(255,153,0,0.14)';
            ctx.fillRect(startX, y1, totalWidth, y2 - y1);
            ctx.strokeStyle = '#ff9900';
            ctx.lineWidth = 1;
            ctx.setLineDash([5, 4]);
            ctx.beginPath();
            ctx.moveTo(startX, y1);
            ctx.lineTo(startX + totalWidth, y1);
            ctx.moveTo(startX, y2);
            ctx.lineTo(startX + totalWidth, y2);
            ctx.stroke();
            ctx.setLineDash([]);
        }
    }

    _drawBadHoleIntervals(ctx, startX, totalWidth, plotTop, plotBottom) {
        if (!Array.isArray(this.badHoleIntervals) || !this.badHoleIntervals.length) return;
        for (const itv of this.badHoleIntervals) {
            const top = Number(itv.top);
            const bottom = Number(itv.bottom);
            if (!Number.isFinite(top) || !Number.isFinite(bottom) || bottom <= top) continue;
            const yTop = this._depthToY(top);
            const yBottom = this._depthToY(bottom);
            if (yBottom < plotTop || yTop > plotBottom) continue;
            const y1 = Math.max(plotTop, yTop);
            const y2 = Math.min(plotBottom, yBottom);
            ctx.fillStyle = 'rgba(220, 38, 38, 0.18)';
            ctx.fillRect(startX, y1, totalWidth, y2 - y1);
            ctx.strokeStyle = 'rgba(220, 38, 38, 0.8)';
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 3]);
            ctx.beginPath();
            ctx.moveTo(startX, y1);
            ctx.lineTo(startX + totalWidth, y1);
            ctx.moveTo(startX, y2);
            ctx.lineTo(startX + totalWidth, y2);
            ctx.stroke();
            ctx.setLineDash([]);
        }
    }

    _drawRFTPoints(ctx, startX, totalWidth, plotTop, plotBottom) {
        if (!Array.isArray(this.rftPoints) || !this.rftPoints.length) return;
        const fluidColor = (f) => {
            const v = String(f || '').toLowerCase();
            if (v === 'oil') return '#2ecc71';
            if (v === 'gas') return '#e74c3c';
            if (v === 'water') return '#3498db';
            return '#aaaaaa';
        };
        const x = startX + totalWidth - 8;
        for (const p of this.rftPoints) {
            const depth = Number(p.depth);
            if (!Number.isFinite(depth)) continue;
            const y = this._depthToY(depth);
            if (y < plotTop || y > plotBottom) continue;
            ctx.fillStyle = fluidColor(p.fluid_type);
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#0d1117';
            ctx.lineWidth = 1;
            ctx.stroke();
        }
    }

    // ─── Export ──────────────────────────────────────────────
    _drawLithTrack(ctx, x, width, plotTop, plotBottom) {
        const lith = this.lithologyData?.lith_code;
        if (!Array.isArray(lith) || !this.depthData.length) return;

        const colorMap = {
            1: '#F5DEB3',
            2: '#D2B48C',
            3: '#808080',
            4: '#87CEEB',
            5: '#FFB6C1',
            6: '#DDA0DD',
            7: '#FFFFFF',
            8: '#2F2F2F',
        };

        ctx.fillStyle = '#0d1117';
        ctx.fillRect(x, plotTop, width, plotBottom - plotTop);
        ctx.strokeStyle = '#30363d';
        ctx.lineWidth = 1;
        ctx.strokeRect(x, plotTop, width, plotBottom - plotTop);

        const len = Math.min(this.depthData.length, lith.length);
        let lastLabelY = -1e9;
        for (let i = 0; i < len; i++) {
            const depth = this.depthData[i];
            if (depth < this.viewStart || depth > this.viewStop) continue;
            const code = Number(lith[i] || 0);
            if (!code || !colorMap[code]) continue;

            const y = this._depthToY(depth);
            const nextDepth = (i + 1 < len) ? this.depthData[i + 1] : depth + (len > 1 ? (this.depthData[1] - this.depthData[0]) : 0.5);
            const y2 = this._depthToY(nextDepth);
            const bh = Math.max(1, Math.abs(y2 - y));

            ctx.fillStyle = colorMap[code];
            ctx.fillRect(x + 1, y - bh / 2, width - 2, bh + 0.5);

            if (Math.abs(y - lastLabelY) > 36) {
                ctx.fillStyle = code === 8 || code === 3 ? '#f8fafc' : '#111827';
                ctx.font = 'bold 9px IBM Plex Mono';
                ctx.textAlign = 'center';
                ctx.fillText(String(code), x + width / 2, y + 3);
                lastLabelY = y;
            }
        }

        ctx.fillStyle = '#8b949e';
        ctx.font = 'bold 9px DM Sans';
        ctx.textAlign = 'center';
        ctx.fillText('LITH', x + width / 2, 16);
    }
    exportPNG() {
        // Create high-res export canvas
        const exportScale = 2;
        const exportCanvas = document.createElement('canvas');
        exportCanvas.width = this.canvas.width;
        exportCanvas.height = this.canvas.height;
        const exportCtx = exportCanvas.getContext('2d');
        exportCtx.scale(this.dpr, this.dpr);

        // Copy current canvas
        exportCtx.drawImage(this.canvas, 0, 0);

        const link = document.createElement('a');
        link.download = `geolog_export_${Date.now()}.png`;
        link.href = exportCanvas.toDataURL('image/png');
        link.click();
    }

    // ─── Statistics ──────────────────────────────────────────
    getCurveStats(mnemonic) {
        const data = this.curveData[mnemonic];
        if (!data || data.length === 0) return null;
        const valid = data.filter(v => v !== null && v !== undefined && !isNaN(v));
        if (valid.length === 0) return null;
        valid.sort((a, b) => a - b);
        const sum = valid.reduce((s, v) => s + v, 0);
        return {
            count: valid.length,
            null_count: data.length - valid.length,
            min: valid[0],
            max: valid[valid.length - 1],
            mean: sum / valid.length,
            median: valid[Math.floor(valid.length / 2)],
            std: Math.sqrt(valid.reduce((s, v) => s + (v - sum / valid.length) ** 2, 0) / valid.length),
        };
    }
}
