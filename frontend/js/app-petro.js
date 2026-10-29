/**
 * Petrophysics, plots, QC and interpretation methods for GeoLogApp.
 * Loaded after app.js and before bootstrap.js.
 */
Object.assign(GeoLogApp.prototype, {
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
        const showGrid = document.getElementById('cpGridLines')?.checked !== false;
        if (showGrid) {
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
        }

        // Schlumberger Neutron-Density overlay
        const slbOverlay = document.getElementById('cpSlbOverlay')?.checked;
        const isNDPlot = (curveX === 'NPHI' && curveY === 'RHOB') || (curveX === 'RHOB' && curveY === 'NPHI');
        if (slbOverlay && isNDPlot) {
            // Force Schlumberger axes: NPHI on X (0.45→-0.15), RHOB on Y (1.95→2.95)
            const slbXMin = -0.15, slbXMax = 0.45;  // NPHI reversed
            const slbYMin = 1.95, slbYMax = 2.95;    // RHOB top=light, bottom=dense

            // Override axis mapping for SLB mode
            const slbToScreenX = (nphi) => margin.left + ((nphi - slbXMin) / (slbXMax - slbXMin)) * plotW;
            const slbToScreenY = (rhob) => margin.top + ((rhob - slbYMin) / (slbYMax - slbYMin)) * plotH;

            // Re-draw points in SLB coordinate space
            ctx.fillStyle = '#58a6ff44';
            ctx.strokeStyle = '#58a6ff';
            ctx.lineWidth = 0.8;
            for (const [px, py] of points) {
                let nphi, rhob;
                if (curveX === 'NPHI') { nphi = px; rhob = py; }
                else { nphi = py; rhob = px; }
                if (nphi < slbXMin || nphi > slbXMax || rhob < slbYMin || rhob > slbYMax) continue;
                const sx = slbToScreenX(nphi);
                const sy = slbToScreenY(rhob);
                ctx.beginPath();
                ctx.arc(sx, sy, 2, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }

            // Lithology reference lines (porosity from 0% to 60%)
            const lithLines = [
                { name: 'Sandstone', rhoMa: 2.65, phiNMa: 0.02, color: '#3fb950' },
                { name: 'Limestone', rhoMa: 2.71, phiNMa: 0.00, color: '#58a6ff' },
                { name: 'Dolomite', rhoMa: 2.87, phiNMa: 0.02, color: '#f2cc60' },
            ];
            const rhoF = 1.0; // water
            const phiNF = 1.0;

            for (const lith of lithLines) {
                ctx.strokeStyle = lith.color;
                ctx.lineWidth = 1.5;
                ctx.setLineDash([]);
                ctx.beginPath();
                let started = false;
                for (let phi = 0; phi <= 0.60; phi += 0.01) {
                    const rhob = phi * rhoF + (1 - phi) * lith.rhoMa;
                    const phiN = phi * phiNF + (1 - phi) * lith.phiNMa;
                    if (rhob < slbYMin || rhob > slbYMax || phiN < slbXMin || phiN > slbXMax) continue;
                    const sx = slbToScreenX(phiN);
                    const sy = slbToScreenY(rhob);
                    if (!started) { ctx.moveTo(sx, sy); started = true; } else ctx.lineTo(sx, sy);
                }
                ctx.stroke();

                // Label at 0% porosity end
                const labelPhi = 0.0;
                const labelRhob = labelPhi * rhoF + (1 - labelPhi) * lith.rhoMa;
                const labelPhiN = labelPhi * phiNF + (1 - labelPhi) * lith.phiNMa;
                if (labelRhob <= slbYMax && labelPhiN >= slbXMin) {
                    ctx.fillStyle = lith.color;
                    ctx.font = 'bold 10px IBM Plex Mono';
                    ctx.textAlign = 'left';
                    ctx.fillText(lith.name, slbToScreenX(labelPhiN) + 4, slbToScreenY(labelRhob) - 4);
                }
            }

            // Porosity iso-lines (horizontal dashed)
            ctx.setLineDash([4, 4]);
            ctx.strokeStyle = '#30363d';
            ctx.lineWidth = 0.8;
            ctx.font = '9px IBM Plex Mono';
            ctx.fillStyle = '#8b949e';
            ctx.textAlign = 'right';
            for (let phi = 0.1; phi <= 0.5; phi += 0.1) {
                // Limestone reference for porosity label
                const rhobLime = phi * rhoF + (1 - phi) * 2.71;
                if (rhobLime < slbYMin || rhobLime > slbYMax) continue;
                const sy = slbToScreenY(rhobLime);
                ctx.beginPath();
                ctx.moveTo(margin.left, sy);
                ctx.lineTo(margin.left + plotW, sy);
                ctx.stroke();
                ctx.fillText((phi * 100).toFixed(0) + '%', margin.left + plotW - 4, sy - 3);
            }
            ctx.setLineDash([]);

            // SLB axis labels (override)
            ctx.fillStyle = '#c9d1d9';
            ctx.font = 'bold 12px DM Sans';
            ctx.textAlign = 'center';
            ctx.fillText('NPHI (v/v) — Schlumberger', margin.left + plotW / 2, canvas.height - 10);
            ctx.save();
            ctx.translate(15, margin.top + plotH / 2);
            ctx.rotate(-Math.PI / 2);
            ctx.fillText('RHOB (g/cc)', 0, 0);
            ctx.restore();

            // SLB axis ticks
            ctx.font = '10px IBM Plex Mono';
            ctx.textAlign = 'center';
            for (let v = -0.1; v <= 0.4; v += 0.1) {
                const sx = slbToScreenX(v);
                ctx.fillText(v.toFixed(1), sx, margin.top + plotH + 18);
            }
            ctx.textAlign = 'right';
            for (let v = 2.0; v <= 2.9; v += 0.1) {
                const sy = slbToScreenY(v);
                ctx.fillText(v.toFixed(1), margin.left - 5, sy + 4);
            }

            // Title
            ctx.fillStyle = '#58a6ff';
            ctx.font = 'bold 12px DM Sans';
            ctx.textAlign = 'left';
            ctx.fillText('Neutron-Density Crossplot (Schlumberger)', margin.left, margin.top - 14);
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
,

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
,

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
,

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

        const safeSatModel = escapeHtml(String(satModel || ''));
        result.innerHTML = `
            <div class="petro-summary">
                <h4>Computed Curves</h4>
                <div class="petro-stat"><span>Sw (avg):</span> <strong>${Number(avg(swValid)).toFixed(3)}</strong></div>
                <div class="petro-stat"><span>Vsh (avg):</span> <strong>${Number(avg(vshValid)).toFixed(3)}</strong></div>
                <div class="petro-stat"><span>PHIE (avg):</span> <strong>${Number(avg(phieValid)).toFixed(3)}</strong></div>
                <hr>
                <h4>Net Pay Quicklook</h4>
                <div class="petro-stat"><span>Cutoffs:</span> <strong>Vsh&lt;${Number(vshCut).toFixed(2)}, PHIE&gt;${Number(phieCut).toFixed(2)}, Sw&lt;${Number(swCut).toFixed(2)}</strong></div>
                <div class="petro-stat"><span>Gross interval:</span> <strong>${Number(gross).toFixed(1)} ft</strong></div>
                <div class="petro-stat"><span>Net pay:</span> <strong>${Number(netPay).toFixed(1)} ft</strong></div>
                <div class="petro-stat"><span>N/G:</span> <strong>${Number(ntg * 100).toFixed(1)}%</strong></div>
                <h4 style="margin-top:10px">Reservoir Interval Table</h4>
                <div style="overflow:auto"><table class="petro-table"><thead><tr><th>Zone</th><th>Top</th><th>Base</th><th>Gross</th><th>PHIE</th><th>Sw</th><th>Vsh</th></tr></thead><tbody>${rows}</tbody></table></div>
                <hr>
                <h4>Saturation Model: ${safeSatModel.charAt(0).toUpperCase() + safeSatModel.slice(1)}</h4>
                <div class="petro-stat"><span>a:</span> <strong>${Number(a)}</strong></div>
                <div class="petro-stat"><span>m:</span> <strong>${Number(m)}</strong></div>
                ${satModel === 'archie' ? '<div class="petro-stat"><span>n:</span> <strong>'+Number(n)+'</strong></div>' : ''}
                <div class="petro-stat"><span>Rw:</span> <strong>${Number(rw)}</strong></div>
            </div>
        `;

        // Refresh viewer
        this.renderer.render();
    }
,

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
                html += `<td style="padding:3px 6px;border:1px solid #21262d;color:#c9d1d9">${escapeHtml(z.name || '-')}</td>`;
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
,

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
,

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
,

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
,

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
,

    async runSensitivity() {
        if (!this.currentWell) return GeoToast.warn('No well selected');
        const iterations = parseInt(document.getElementById('sensIter')?.value || '1000', 10);
        const pct = parseFloat(document.getElementById('sensPct')?.value || '25');
        const rwPct = parseFloat(document.getElementById('sensRwPct')?.value || String(pct));
        const mPct = parseFloat(document.getElementById('sensMPct')?.value || String(pct));
        const nPct = parseFloat(document.getElementById('sensNPct')?.value || String(pct));
        const vshCutPct = parseFloat(document.getElementById('sensVshCutPct')?.value || String(pct));
        const phieCutPct = parseFloat(document.getElementById('sensPhieCutPct')?.value || String(pct));
        const swCutPct = parseFloat(document.getElementById('sensSwCutPct')?.value || String(pct));
        const model = document.getElementById('satModel')?.value || 'archie';
        const getVal = (id) => parseFloat(document.getElementById(id)?.value || '0');

        GeoLoading.show('Running Monte Carlo (' + iterations + ' iterations)...');
        try {
            const result = await this._api(`/wells/${this.currentWell.id}/sensitivity`, {
                method: 'POST',
                body: JSON.stringify({
                    a: getVal('archA'), m: getVal('archM'), n: getVal('archN'), rw: getVal('archRw'),
                    vsh_cutoff: getVal('cutVsh'), phie_cutoff: getVal('cutPhie'), sw_cutoff: getVal('cutSw'),
                    saturation_model: model,
                    iterations,
                    variation_pct: pct,
                    rw_variation_pct: rwPct,
                    m_variation_pct: mPct,
                    n_variation_pct: nPct,
                    vsh_cutoff_variation_pct: vshCutPct,
                    phie_cutoff_variation_pct: phieCutPct,
                    sw_cutoff_variation_pct: swCutPct,
                }),
            });

            const profile = result.variation_profile || {};
            const driverRows = (result.drivers || []).map((d) => {
                const sign = d.correlation >= 0 ? '+' : '−';
                return `<div class="petro-stat"><span>${escapeHtml(String(d.parameter || ''))}</span><strong>${sign}${Math.abs(d.correlation).toFixed(3)} corr</strong></div>`;
            }).join('') || '<div class="petro-stat"><span>Drivers</span><strong>N/A</strong></div>';

            const panel = document.getElementById('sensResults');
            if (!panel) return;

            panel.innerHTML = `
                <div class="petro-summary">
                    <h4>Monte Carlo Uncertainty</h4>
                    <div class="petro-stat"><span>Iterations:</span> <strong>${Number(result.iterations) || 0}</strong></div>
                    <div class="petro-stat"><span>Saturation model:</span> <strong>${escapeHtml(String(model || ''))}</strong></div>
                    <div class="petro-stat"><span>Mean ± Std:</span> <strong>${escapeHtml(String(result.mean_net_pay ?? 0))} ± ${escapeHtml(String(result.std_net_pay ?? 0))} ft</strong></div>
                    <hr>
                    <h4>Net Pay Percentiles</h4>
                    <div class="petro-stat"><span>P90 (conservative low):</span> <strong style="color:#f85149">${escapeHtml(String(result.p90_net_pay ?? 0))} ft</strong></div>
                    <div class="petro-stat"><span>P50 (median):</span> <strong style="color:#d29922">${escapeHtml(String(result.p50_net_pay ?? 0))} ft</strong></div>
                    <div class="petro-stat"><span>P10 (optimistic high):</span> <strong style="color:#3fb950">${escapeHtml(String(result.p10_net_pay ?? 0))} ft</strong></div>
                    <hr>
                    <h4>Uncertainty Profile (±%)</h4>
                    <div class="petro-stat"><span>Rw/m/n:</span> <strong>${escapeHtml(String(profile.rw ?? 0))}/${escapeHtml(String(profile.m ?? 0))}/${escapeHtml(String(profile.n ?? 0))}</strong></div>
                    <div class="petro-stat"><span>Vsh/PHIE/Sw cut:</span> <strong>${escapeHtml(String(profile.vsh_cutoff ?? 0))}/${escapeHtml(String(profile.phie_cutoff ?? 0))}/${escapeHtml(String(profile.sw_cutoff ?? 0))}</strong></div>
                    <hr>
                    <h4>Top Drivers (Correlation)</h4>
                    ${driverRows}
                    <h4 style="margin-top:12px">Tornado (P90↔P10 spread)</h4>
                    <canvas id="tornadoCanvas" width="500" height="250"></canvas>
                    <h4 style="margin-top:12px">Distribution</h4>
                    <canvas id="sensHistogram" width="500" height="160"></canvas>
                </div>
            `;

            this._drawTornado(result);
            this._drawSensHistogram(result);
        } catch (e) {
            GeoToast.error('Sensitivity failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    }
,

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
,

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
,

    async runRwEstimation() {
        if (!this.currentWell) return GeoToast.warn('Select a well first');
        const getNum = (id, fallback = null) => {
            const el = document.getElementById(id);
            const v = el ? parseFloat(el.value) : NaN;
            return Number.isFinite(v) ? v : fallback;
        };
        const method = (document.getElementById('rwMethod')?.value || 'all').toLowerCase();
        const payload = {
            method,
            rmf: getNum('rwRmf'),
            temperature: getNum('rwTemp'),
            temperature_unit: document.getElementById('rwTempUnit')?.value || 'F',
            ssp: getNum('rwSsp'),
            rt_clean: getNum('rwRtClean'),
            phi_clean: getNum('rwPhiClean'),
            m: getNum('rwM', 2.0),
            rt_curve: 'RT',
            phi_curve: 'NPHI',
        };

        GeoLoading.show('Estimating Rw...');
        try {
            const out = await this._api(`/wells/${this.currentWell.id}/rw-estimation`, {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            this._lastRwEstimation = out;
            const sp = out.methods?.sp;
            const ro = out.methods?.ro;
            const hi = out.methods?.hingle;
            const fmt = (v, n = 4) => (v === null || v === undefined || Number.isNaN(v)) ? 'N/A' : Number(v).toFixed(n);
            const catalog = out.catalog || {};
            const cat = (arr) => Array.isArray(arr) && arr.length === 2 ? `${arr[0]} - ${arr[1]}` : 'N/A';
            const html = `
                <div class="petro-summary">
                    <div class="petro-stat"><span>SP Rw</span><strong>${fmt(sp?.rw)} Ω·m</strong></div>
                    <div class="petro-stat"><span>SP Rw@77°F</span><strong>${fmt(sp?.rw_77f)} Ω·m</strong></div>
                    <div class="petro-stat"><span>Ro Rw</span><strong>${fmt(ro?.rw)} Ω·m</strong></div>
                    <div class="petro-stat"><span>Hingle Rw</span><strong>${fmt(hi?.rw)} Ω·m</strong></div>
                    <div class="petro-stat"><span>Hingle R²</span><strong>${fmt(hi?.r2, 3)}</strong></div>
                    <div class="petro-stat"><span>Recommended Rw</span><strong style="color:#3fb950">${fmt(out.recommended_rw)} Ω·m</strong></div>
                    <div class="petro-stat"><span>Confidence</span><strong>${fmt(out.confidence_score, 1)}%</strong></div>
                </div>
                <div style="margin-top:8px;color:#8b949e;font-size:11px">
                    Catalog: Fresh ${cat(catalog.fresh_water_ohm_m)} • Saline ${cat(catalog.saline_water_ohm_m)} • Gulf Coast ${cat(catalog.typical_gulf_coast_ohm_m)} • North Sea ${cat(catalog.typical_north_sea_ohm_m)}
                </div>`;
            document.getElementById('rwResults').innerHTML = html;
            this._drawRwHingleCanvas(hi?.crossplot, hi);
            GeoToast.success('Rw estimation complete');
        } catch (e) {
            GeoToast.error(e.message || String(e));
        } finally {
            GeoLoading.hide();
        }
    }
,

    _drawRwHingleCanvas(crossplot, hingle) {
        const canvas = document.getElementById('rwHingleCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const W = canvas.clientWidth || 480;
        const H = canvas.clientHeight || 220;
        canvas.width = W;
        canvas.height = H;
        const m = { top: 22, right: 16, bottom: 30, left: 42 };
        const plotW = W - m.left - m.right;
        const plotH = H - m.top - m.bottom;

        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, W, H);

        const xs = crossplot?.x_phi || [];
        const ys = crossplot?.y_inv_rt || [];
        if (!xs.length || !ys.length) {
            ctx.fillStyle = '#8b949e';
            ctx.font = '12px DM Sans';
            ctx.fillText('No Hingle crossplot data', 12, 22);
            return;
        }

        const xMin = Math.min(...xs), xMax = Math.max(...xs);
        const yMin = Math.min(...ys), yMax = Math.max(...ys);
        const xr = (xMax - xMin) || 1;
        const yr = (yMax - yMin) || 1;
        const xp = (x) => m.left + ((x - xMin) / xr) * plotW;
        const yp = (y) => m.top + plotH - ((y - yMin) / yr) * plotH;

        ctx.strokeStyle = '#30363d';
        ctx.strokeRect(m.left, m.top, plotW, plotH);

        ctx.fillStyle = '#58a6ff99';
        for (let i = 0; i < xs.length; i++) {
            ctx.beginPath();
            ctx.arc(xp(xs[i]), yp(ys[i]), 2, 0, Math.PI * 2);
            ctx.fill();
        }

        if (hingle && Number.isFinite(hingle.slope) && Number.isFinite(hingle.intercept_rwa)) {
            ctx.strokeStyle = '#f85149';
            ctx.lineWidth = 1.5;
            const y1 = hingle.slope * xMin + hingle.intercept_rwa;
            const y2 = hingle.slope * xMax + hingle.intercept_rwa;
            ctx.beginPath();
            ctx.moveTo(xp(xMin), yp(y1));
            ctx.lineTo(xp(xMax), yp(y2));
            ctx.stroke();
        }

        ctx.fillStyle = '#8b949e';
        ctx.font = '10px IBM Plex Mono';
        ctx.fillText('φ', W / 2, H - 6);
        ctx.save();
        ctx.translate(10, H / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('1/Rt', 0, 0);
        ctx.restore();
    }
,

    async applyRecommendedRw() {
        const rw = this._lastRwEstimation?.recommended_rw;
        if (!Number.isFinite(rw)) return GeoToast.warn('Run Rw estimation first');
        const archRw = document.getElementById('archRw');
        if (!archRw) return GeoToast.warn('Petrophysics Rw input not found');
        archRw.value = Number(rw).toFixed(4);
        GeoToast.success(`Rw updated to ${Number(rw).toFixed(4)} Ω·m`);
    }
,

    async runLQCShoulderBedCorrection() {
        if (!this.currentLogRun) return GeoToast.warn('Select a log run');
        const mnemonic = document.getElementById('lqcCurveSelect')?.value;
        const bedThreshold = parseFloat(document.getElementById('lqcBedThreshold')?.value || '2');
        const method = document.getElementById('lqcMethod')?.value || 'linear';
        if (!mnemonic) return GeoToast.warn('Select curve for LQC');
        GeoLoading.show('Running shoulder-bed correction...');
        try {
            const out = await this._api(`/log-runs/${this.currentLogRun.id}/shoulder-bed-correction`, {
                method: 'POST',
                body: JSON.stringify({ mnemonic, bed_thickness_threshold: bedThreshold, method }),
            });
            const original = Array.isArray(this.renderer?.curveData?.[mnemonic]) ? [...this.renderer.curveData[mnemonic]] : null;
            this.lqcState = {
                result: out,
                originalCurve: original,
                correctedCurve: out.corrected_curve || null,
                activeMnemonic: mnemonic,
                showCorrected: false,
            };
            const toggle = document.getElementById('lqcToggleCorrected');
            if (toggle) toggle.checked = false;
            this.toggleLQCCorrected(false);
            this.renderer?.setBadHoleIntervals(out?.bad_hole?.intervals || []);
            this._renderLQCResults();
            GeoToast.success('LQC completed');
        } catch (e) {
            GeoToast.error('LQC failed: ' + (e.message || e));
        } finally {
            GeoLoading.hide();
        }
    }
,

    toggleLQCCorrected(enabled) {
        this.lqcState.showCorrected = !!enabled;
        const m = this.lqcState.activeMnemonic;
        if (!m || !this.renderer?.curveData) return;
        if (enabled && Array.isArray(this.lqcState.correctedCurve)) {
            this.renderer.curveData[m] = [...this.lqcState.correctedCurve];
        } else if (Array.isArray(this.lqcState.originalCurve)) {
            this.renderer.curveData[m] = [...this.lqcState.originalCurve];
        }
        this.renderer.render();
    }
,

    _renderLQCResults() {
        const sumEl = document.getElementById('lqcSummary');
        const intEl = document.getElementById('lqcIntervals');
        const out = this.lqcState.result;
        if (!sumEl || !intEl) return;
        if (!out) {
            sumEl.textContent = 'Run LQC to see summary.';
            intEl.innerHTML = '';
            return;
        }
        const q = out.qc_summary || {};
        sumEl.innerHTML = `Thin beds: <strong>${q.thin_beds_pct ?? 0}%</strong> • Bad hole: <strong>${q.bad_hole_pct ?? 0}%</strong> • Invaded: <strong>${q.invaded_pct ?? 0}%</strong>`;

        const thinRows = (out.thin_beds || []).slice(0, 150).map((b, i) =>
            `<div style="padding:4px 0;border-bottom:1px solid #21262d"><span style="color:#facc15">Thin #${i + 1}</span> ${b.top} - ${b.bottom} ft <span style="color:#8b949e">(${b.thickness} ft)</span></div>`
        ).join('');
        const badRows = (out?.bad_hole?.intervals || []).slice(0, 150).map((b, i) =>
            `<div style="padding:4px 0;border-bottom:1px solid #21262d"><span style="color:#ef4444">BadHole #${i + 1}</span> ${b.top} - ${b.bottom} ft <span style="color:#8b949e">(${b.thickness} ft)</span></div>`
        ).join('');

        intEl.innerHTML = `<div style="margin-bottom:6px;color:#8b949e">Flagged intervals</div>${thinRows || '<div style="color:#8b949e">No thin beds flagged.</div>'}${badRows || '<div style="color:#8b949e;margin-top:8px">No bad-hole intervals flagged.</div>'}`;
    }
,

    async runPermeabilityModels() {
        if (!this.currentWell) return GeoToast.warn('Select a well first');
        const model = document.getElementById('permModel')?.value || 'all';
        const swir = parseFloat(document.getElementById('permSwir')?.value || '0.2');
        const waterCut = parseFloat(document.getElementById('permWaterCut')?.value || '0');
        const timurA = parseFloat(document.getElementById('permTimurA')?.value || '0.136');
        const coatesC = parseFloat(document.getElementById('permCoatesC')?.value || '10000');
        const sdrA = parseFloat(document.getElementById('permSdrA')?.value || '4');

        GeoLoading.show('Computing permeability models...');
        try {
            const data = await this._api(`/wells/${this.currentWell.id}/permeability`, {
                method: 'POST',
                body: JSON.stringify({
                    model,
                    swir: Number.isFinite(swir) ? swir : 0.2,
                    water_cut: Number.isFinite(waterCut) ? waterCut : 0,
                    timur_a: Number.isFinite(timurA) ? timurA : 0.136,
                    coates_c: Number.isFinite(coatesC) ? coatesC : 10000,
                    sdr_a: Number.isFinite(sdrA) ? sdrA : 4,
                })
            });
            this.permResults = data;
            this._renderPermeabilityResults(data);
            GeoToast.success(`Permeability computed (${(data.models_computed || []).join(', ')})`);
        } catch (e) {
            GeoToast.error('Permeability failed: ' + (e.message || e));
        } finally {
            GeoLoading.hide();
        }
    }
,

    applyPermeabilityToViewer(model = null) {
        if (!this.permResults || !this.renderer) return GeoToast.warn('Run permeability first');
        const chosen = model || (document.getElementById('permApplyModel')?.value || this.permResults.models_computed?.[0]);
        const k = this.permResults?.k_values?.[chosen];
        const d = this.permResults?.depth;
        if (!k || !d || !k.length || d.length !== k.length) return GeoToast.warn('No model data to overlay');

        this.renderer.depthData = d.slice();
        this.renderer.curveData['PERM'] = k.map(v => (v == null || Number.isNaN(v)) ? NaN : Number(v));
        this.curveConfig['PERM'] = { track: 4, color: '#ff7b72', scale: [0.01, Math.max(1, ...k.filter(v => Number.isFinite(v)) || [1000])], unit: 'mD', name: `PERM (${chosen.toUpperCase()})`, log: true };
        this.renderer.curveConfig = this.curveConfig;
        this.renderer.render();
        GeoToast.success(`PERM (${chosen.toUpperCase()}) overlay added`);
    }
,

    _renderPermeabilityResults(data) {
        const container = document.getElementById('permResults');
        const curveCanvas = document.getElementById('permCurveCanvas');
        const xplotCanvas = document.getElementById('permCrossplotCanvas');
        const fziCanvas = document.getElementById('permFziCanvas');
        if (!container || !curveCanvas || !xplotCanvas || !fziCanvas) return;

        const models = data.models_computed || [];
        const colors = { coates: '#58a6ff', timur: '#3fb950', sdr: '#d29922' };

        const sel = document.getElementById('permApplyModel');
        if (sel) sel.innerHTML = models.map(m => `<option value="${m}">${m.toUpperCase()}</option>`).join('');

        let html = '<table class="petro-table"><tr><th>Model</th><th>Points</th><th>Min (mD)</th><th>Mean (mD)</th><th>Max (mD)</th></tr>';
        for (const m of models) {
            const s = data.summary?.[m] || {};
            html += `<tr><td style="color:${colors[m] || '#c9d1d9'}">${m.toUpperCase()}</td><td>${s.count ?? 0}</td><td>${s.min ?? '—'}</td><td>${s.mean ?? '—'}</td><td>${s.max ?? '—'}</td></tr>`;
        }
        html += '</table>';
        container.innerHTML = html;

        this._plotPermCurve(curveCanvas, data.depth || [], data.k_values || {}, models, colors);
        this._plotPermCrossplot(xplotCanvas, data.crossplot || {}, models, colors);
        this._plotFziHistogram(fziCanvas, data.fzi || {}, models[0], colors);
    }
,

    _plotPermCurve(canvas, depth, kv, models, colors) {
        const ctx = canvas.getContext('2d');
        const W = canvas.parentElement.getBoundingClientRect().width || 800;
        canvas.width = W * 2; canvas.height = 560; ctx.scale(2, 2);
        const H = 280, pad = { top: 20, right: 20, bottom: 30, left: 55 }, pw = W - pad.left - pad.right, ph = H - pad.top - pad.bottom;
        ctx.fillStyle = '#0a0e14'; ctx.fillRect(0, 0, W, H);
        if (!depth?.length) return;
        const dMin = Math.min(...depth), dMax = Math.max(...depth);
        const allK = models.flatMap(m => (kv[m] || []).filter(v => Number.isFinite(v) && v > 0));
        if (!allK.length) return;
        const kMin = Math.log10(Math.max(1e-4, Math.min(...allK))), kMax = Math.log10(Math.max(...allK));
        const sx = (k) => pad.left + ((Math.log10(Math.max(1e-4, k)) - kMin) / Math.max(1e-9, (kMax - kMin))) * pw;
        const sy = (d) => pad.top + ((d - dMin) / Math.max(1e-9, (dMax - dMin))) * ph;
        for (const m of models) {
            ctx.strokeStyle = colors[m] || '#c9d1d9'; ctx.lineWidth = 1.2; ctx.beginPath();
            let started = false;
            const arr = kv[m] || [];
            for (let i = 0; i < Math.min(arr.length, depth.length); i++) {
                const v = arr[i];
                if (!Number.isFinite(v) || v <= 0) continue;
                const x = sx(v), y = sy(depth[i]);
                if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }
    }
,

    _plotPermCrossplot(canvas, crossplot, models, colors) {
        const model = models[0];
        const cp = crossplot?.[model];
        const ctx = canvas.getContext('2d');
        const W = canvas.parentElement.getBoundingClientRect().width || 800;
        canvas.width = W * 2; canvas.height = 560; ctx.scale(2, 2);
        const H = 280, pad = { top: 20, right: 20, bottom: 30, left: 55 }, pw = W - pad.left - pad.right, ph = H - pad.top - pad.bottom;
        ctx.fillStyle = '#0a0e14'; ctx.fillRect(0, 0, W, H);
        if (!cp?.phi?.length) return;
        const xMin = Math.min(...cp.phi), xMax = Math.max(...cp.phi);
        const yLog = cp.k.map(v => Math.log10(Math.max(1e-4, v)));
        const yMin = Math.min(...yLog), yMax = Math.max(...yLog);
        const sx = (x) => pad.left + ((x - xMin) / Math.max(1e-9, (xMax - xMin))) * pw;
        const sy = (y) => pad.top + ph - ((y - yMin) / Math.max(1e-9, (yMax - yMin))) * ph;
        ctx.fillStyle = colors[model] || '#58a6ff';
        cp.phi.forEach((x, i) => { const y = yLog[i]; ctx.fillRect(sx(x), sy(y), 2, 2); });
        if (cp.k_fit?.length === cp.phi.length) {
            ctx.strokeStyle = '#f85149'; ctx.beginPath();
            cp.phi.forEach((x, i) => { const y = Math.log10(Math.max(1e-4, cp.k_fit[i])); if (i===0) ctx.moveTo(sx(x), sy(y)); else ctx.lineTo(sx(x), sy(y)); });
            ctx.stroke();
        }
        ctx.fillStyle = '#c9d1d9'; ctx.font = '12px Geologica';
        ctx.fillText(`${model.toUpperCase()}  R²=${cp.r2 ?? 'n/a'}`, pad.left + 8, pad.top + 14);
    }
,

    _plotFziHistogram(canvas, fzi, model, colors) {
        const hist = fzi?.[model]?.histogram || [];
        const ctx = canvas.getContext('2d');
        const W = canvas.parentElement.getBoundingClientRect().width || 800;
        canvas.width = W * 2; canvas.height = 400; ctx.scale(2, 2);
        const H = 200, pad = { top: 20, right: 20, bottom: 25, left: 40 }, pw = W - pad.left - pad.right, ph = H - pad.top - pad.bottom;
        ctx.fillStyle = '#0a0e14'; ctx.fillRect(0, 0, W, H);
        if (!hist.length) return;
        const maxC = Math.max(...hist.map(h => h.count), 1);
        const bw = pw / hist.length;
        ctx.fillStyle = colors[model] || '#d29922';
        hist.forEach((h, i) => {
            const bh = (h.count / maxC) * ph;
            ctx.fillRect(pad.left + i * bw + 1, pad.top + ph - bh, Math.max(2, bw - 2), bh);
        });
    }
,

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
,

    async runElectrofaciesAsync() {
        if (!this.currentWell || !this.currentLogRun) return GeoToast.warn('Load a well first');
        const n = parseInt(document.getElementById('faciesN')?.value || '4');
        const checks = document.querySelectorAll('#faciesCurveCheckboxes input:checked');
        const curves = Array.from(checks).map(c => c.value);
        if (curves.length < 2) return GeoToast.warn('Select at least 2 curves');
        GeoLoading.show('Queueing electrofacies job...');
        try {
            const res = await this._api('/wells/' + this.currentWell.id + '/electrofacies-async', {
                method: 'POST', body: JSON.stringify({ log_run_id: this.currentLogRun.id, n_clusters: n, curves })
            });
            this._trackJob(res.job_id);
            GeoToast.success('Electrofacies job queued: ' + res.job_id);
        } catch (e) { GeoToast.error('Queue failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    }
,

    async toggleLithTrack(forceOn = false) {
        if (!this.renderer) return;
        this._showLithTrack = forceOn ? true : !this._showLithTrack;
        this.renderer._showLithology = this._showLithTrack;

        if (!this._showLithTrack) {
            this.renderer.setLithologyData(null);
            this._renderLithologyLegend();
            this.renderer.render();
            GeoToast.info('Lith track: OFF');
            return;
        }

        if (!this.currentWell) {
            GeoToast.warn('Load a well first');
            this._showLithTrack = false;
            this.renderer._showLithology = false;
            return;
        }

        try {
            GeoLoading.show('Classifying lithology...');
            const grMin = parseFloat(document.getElementById('lithGrMin')?.value || '0');
            const grMax = parseFloat(document.getElementById('lithGrMax')?.value || '150');
            const method = document.getElementById('lithMethod')?.value || 'gr_rhob_nphi';
            this._lithologyData = await this._api(`/wells/${this.currentWell.id}/lithology`, {
                method: 'POST',
                body: JSON.stringify({
                    log_run_id: this.currentLogRun?.id,
                    gr_min: grMin,
                    gr_max: grMax,
                    method,
                }),
            });
            this.renderer.setLithologyData(this._lithologyData);
            this._renderLithologyLegend();
            GeoToast.info('Lith track: ON');
        } catch (e) {
            this._showLithTrack = false;
            this.renderer._showLithology = false;
            this.renderer.setLithologyData(null);
            this._renderLithologyLegend();
            GeoToast.error('Lithology failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    }
,

    _renderLithologyLegend() {
        const el = document.getElementById('lithologyLegend');
        if (!el) return;
        if (!this._showLithTrack || !this._lithologyData?.summary) {
            el.style.display = 'none';
            el.innerHTML = '';
            return;
        }
        const items = [
            { code: 1, name: 'Sand', color: '#F5DEB3' },
            { code: 2, name: 'Shaly sand', color: '#D2B48C' },
            { code: 3, name: 'Shale', color: '#808080' },
            { code: 4, name: 'Limestone', color: '#87CEEB' },
            { code: 5, name: 'Dolomite', color: '#FFB6C1' },
            { code: 6, name: 'Anhydrite', color: '#DDA0DD' },
            { code: 7, name: 'Salt', color: '#FFFFFF' },
            { code: 8, name: 'Coal', color: '#2F2F2F' },
        ];
        const pct = this._lithologyData.summary || {};
        const pctKey = {
            1: 'sand', 2: 'shaly_sand', 3: 'shale', 4: 'limestone',
            5: 'dolomite', 6: 'anhydrite', 7: 'salt', 8: 'coal'
        };
        let html = '<div style="font-weight:600;margin-bottom:6px">Lithology Legend</div><div style="display:flex;flex-wrap:wrap;gap:8px">';
        for (const it of items) {
            html += `<div style="display:flex;align-items:center;gap:6px;padding:2px 6px;border:1px solid #30363d;border-radius:5px">` +
                `<span style="display:inline-block;width:12px;height:12px;background:${it.color};border:1px solid #475569"></span>` +
                `<span>${it.code} ${it.name}${pct[pctKey[it.code]] != null ? ` (${pct[pctKey[it.code]]}%)` : ''}</span></div>`;
        }
        html += '</div>';
        el.innerHTML = html;
        el.style.display = 'block';
    }
,

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
,

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
,

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
,

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
,

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
,

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
,

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
,

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
,

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
,

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
,

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
,

    async runTornado() {
        if (!this.currentWell) { GeoToast.warn('Select a well first'); return; }
        const variation = document.getElementById('tornadoVar')?.value || 20;
        GeoLoading.show('Running tornado analysis...');
        try {
            const resp = await fetch(`/api/wells/${this.currentWell.id}/tornado`, {
                method: 'POST', headers: { 'Content-Type': 'application/json', ...this._authHeaders() },
                body: JSON.stringify({ variation_pct: parseFloat(variation) })
            });
            const data = await resp.json();
            GeoLoading.hide();
            this._renderTornado(data);
        } catch (e) {
            GeoLoading.hide();
            GeoToast.error('Tornado analysis failed: ' + e.message);
        }
    }
,

    _renderTornado(data) {
        const container = document.getElementById('tornadoResults');
        if (!container) return;
        const maxImpact = Math.max(...data.tornado.map(t => Math.abs(t.swing_low)), ...data.tornado.map(t => Math.abs(t.swing_high)), 1);

        let html = `<div style="margin-bottom:16px">
            <span class="qc-grade qc-grade-a" style="font-size:20px">Base Net Pay: ${data.base_pay} ft</span>
            <span style="color:var(--text-muted);margin-left:12px">±${data.variation_pct}% variation</span>
        </div>`;

        html += '<div style="display:flex;flex-direction:column;gap:8px">';
        data.tornado.forEach((item, idx) => {
            const barLow = Math.abs(item.swing_low) / maxImpact * 100;
            const barHigh = Math.abs(item.swing_high) / maxImpact * 100;
            const color = idx === 0 ? 'var(--danger)' : idx === 1 ? 'var(--warning)' : 'var(--accent)';
            html += `<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg-tertiary);border-radius:6px;border-left:3px solid ${color}">
                <div style="min-width:100px;font-weight:600;font-size:12px;color:var(--text-primary)">${item.parameter}</div>
                <div style="flex:1;display:flex;align-items:center;gap:4px">
                    <div style="text-align:right;width:60px;font-family:var(--font-mono);font-size:11px;color:var(--danger)">${item.swing_low > 0 ? '+' : ''}${item.swing_low}</div>
                    <div style="flex:1;height:20px;background:var(--bg-primary);border-radius:3px;position:relative;overflow:hidden">
                        <div style="position:absolute;right:50%;width:${barLow/2}%;height:100%;background:rgba(199,90,90,0.4);border-radius:3px 0 0 3px"></div>
                        <div style="position:absolute;left:50%;width:${barHigh/2}%;height:100%;background:rgba(76,175,125,0.4);border-radius:0 3px 3px 0"></div>
                        <div style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--text-muted)"></div>
                    </div>
                    <div style="width:60px;font-family:var(--font-mono);font-size:11px;color:var(--success)">+${item.swing_high}</div>
                </div>
                <div style="min-width:50px;text-align:right;font-family:var(--font-mono);font-size:11px;color:var(--text-muted)">${item.impact} ft</div>
            </div>`;
        });
        html += '</div>';
        html += '<div style="margin-top:12px;font-size:11px;color:var(--text-muted);text-align:center">← Low value reduces pay | High value increases pay →</div>';

        container.innerHTML = html;
        container.className = '';
        container.style.padding = '0';
    }
,

    async runVclModels() {
        if (!this.currentWell) { GeoToast.warn('Select a well first'); return; }
        const grClean = parseFloat(document.getElementById('vclGrClean')?.value || 20);
        const grShale = parseFloat(document.getElementById('vclGrShale')?.value || 120);
        GeoLoading.show('Computing Vclay models...');
        try {
            const resp = await fetch(`/api/wells/${this.currentWell.id}/vcl-models`, {
                method: 'POST', headers: { 'Content-Type': 'application/json', ...this._authHeaders() },
                body: JSON.stringify({ gr_clean: grClean, gr_shale: grShale })
            });
            const data = await resp.json();
            GeoLoading.hide();
            this._renderVclModels(data);
        } catch (e) {
            GeoLoading.hide();
            GeoToast.error('Vcl computation failed');
        }
    }
,

    _renderVclModels(data) {
        const container = document.getElementById('vclResults');
        if (!container) return;
        const models = ['igr', 'larionov_tertiary', 'larionov_old', 'clavier', 'steiber'];
        const labels = { igr: 'Linear IGR', larionov_tertiary: 'Larionov (Tertiary)', larionov_old: 'Larionov (Older)', clavier: 'Clavier', steiber: 'Steiber' };
        const colors = ['#5b8fb9', '#d4a853', '#4caf7d', '#c75a5a', '#8b6fb0'];

        let html = `<div style="margin-bottom:16px"><span style="color:var(--text-muted);font-size:12px">GR Clean: ${data.params.gr_clean} | GR Shale: ${data.params.gr_shale}</span></div>`;

        // Summary table
        html += '<table class="petro-table"><tr><th>Model</th><th>Mean</th><th>Median</th><th>Min</th><th>Max</th></tr>';
        models.forEach((m, idx) => {
            const s = data.summary[m];
            html += `<tr><td style="color:${colors[idx]};font-weight:600">${labels[m]}</td>
                <td>${s.mean?.toFixed(4) || '—'}</td><td>${s.median?.toFixed(4) || '—'}</td>
                <td>${s.min?.toFixed(4) || '—'}</td><td>${s.max?.toFixed(4) || '—'}</td></tr>`;
        });
        html += '</table>';

        // Canvas for depth plot
        html += '<div style="margin-top:20px"><canvas id="vclCanvas" style="width:100%;height:400px;background:var(--bg-primary);border-radius:8px"></canvas></div>';

        container.innerHTML = html;
        container.className = '';
        container.style.padding = '0';

        // Render the depth plot
        setTimeout(() => this._renderVclPlot(data, colors), 100);
    }
,

    _renderVclPlot(data, colors) {
        const canvas = document.getElementById('vclCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width * 2;
        canvas.height = 800;
        ctx.scale(2, 2);
        const W = rect.width, H = 400;
        const pad = { top: 20, right: 20, bottom: 40, left: 60 };
        const pw = W - pad.left - pad.right;
        const ph = H - pad.top - pad.bottom;

        ctx.fillStyle = '#0a0e14';
        ctx.fillRect(0, 0, W, H);

        const depth = data.results.depth;
        const dMin = Math.min(...depth);
        const dMax = Math.max(...depth);
        const models = ['igr', 'larionov_tertiary', 'larionov_old', 'clavier', 'steiber'];
        const labels = ['IGR', 'Larionov (T)', 'Larionov (O)', 'Clavier', 'Steiber'];

        // Grid
        ctx.strokeStyle = 'rgba(42,52,70,0.5)';
        ctx.lineWidth = 0.5;
        for (let i = 0; i <= 4; i++) {
            const x = pad.left + (pw / 4) * i;
            ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + ph); ctx.stroke();
            ctx.fillStyle = '#6b7a8d';
            ctx.font = '10px JetBrains Mono';
            ctx.textAlign = 'center';
            ctx.fillText((i * 0.25).toFixed(2), x, H - 10);
        }
        for (let i = 0; i <= 5; i++) {
            const y = pad.top + (ph / 5) * i;
            ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + pw, y); ctx.stroke();
            ctx.fillStyle = '#6b7a8d';
            ctx.font = '10px JetBrains Mono';
            ctx.textAlign = 'right';
            ctx.fillText((dMin + (dMax - dMin) / 5 * i).toFixed(0), pad.left - 8, y + 4);
        }

        // Plot each model
        const step = Math.max(1, Math.floor(depth.length / 500));
        models.forEach((model, idx) => {
            ctx.strokeStyle = colors[idx];
            ctx.lineWidth = 1.5;
            ctx.globalAlpha = 0.8;
            ctx.beginPath();
            let started = false;
            for (let i = 0; i < depth.length; i += step) {
                const v = data.results[model][i];
                if (v === null || v === undefined || isNaN(v)) continue;
                const px = pad.left + v * pw;
                const py = pad.top + ((depth[i] - dMin) / (dMax - dMin)) * ph;
                if (!started) { ctx.moveTo(px, py); started = true; }
                else ctx.lineTo(px, py);
            }
            ctx.stroke();
            ctx.globalAlpha = 1;
        });

        // Legend
        ctx.font = '11px Geologica';
        models.forEach((m, idx) => {
            const lx = pad.left + 10 + idx * 100;
            const ly = pad.top - 5;
            ctx.fillStyle = colors[idx];
            ctx.fillRect(lx, ly - 8, 12, 3);
            ctx.fillText(labels[idx], lx + 16, ly);
        });
    }
,

    showCoreCalModal() {
        if (!this.currentWell) { GeoToast.warn('Select a well first'); return; }
        GeoModal.show({
            title: 'Core Calibration Data',
            fields: [
                { id: 'core_depths', label: 'Core Depths (comma-separated, ft)', type: 'text', placeholder: '5100, 5200, 5300, 5400' },
                { id: 'core_phi', label: 'Core Porosity (comma-separated, v/v)', type: 'text', placeholder: '0.18, 0.22, 0.15, 0.20' },
                { id: 'core_perm', label: 'Core Permeability (comma-separated, mD, optional)', type: 'text', placeholder: '120, 350, 45, 200' },
            ],
            onConfirm: (vals) => {
                const depths = vals.core_depths.split(',').map(Number).filter(n => !isNaN(n));
                const phi = vals.core_phi.split(',').map(Number).filter(n => !isNaN(n));
                const perm = vals.core_perm ? vals.core_perm.split(',').map(Number).filter(n => !isNaN(n)) : [];
                this._runCoreCal(depths, phi, perm);
            }
        });
    }
,

    async _runCoreCal(depths, phi, perm) {
        const curve = document.getElementById('coreCalCurve')?.value || 'NPHI';
        GeoLoading.show('Calibrating...');
        try {
            const resp = await fetch(`/api/wells/${this.currentWell.id}/core-calibration`, {
                method: 'POST', headers: { 'Content-Type': 'application/json', ...this._authHeaders() },
                body: JSON.stringify({ core_depth: depths, core_phi: phi, core_k: perm, log_curve: curve })
            });
            const data = await resp.json();
            GeoLoading.hide();
            this._renderCoreCal(data, curve);
        } catch (e) {
            GeoLoading.hide();
            GeoToast.error('Calibration failed: ' + (e.message || 'Unknown error'));
        }
    }
,

    _renderCoreCal(data, curve) {
        const container = document.getElementById('coreCalResults');
        if (!container) return;

        let html = `<div class="stats-card" style="margin-bottom:16px">
            <h4 style="color:var(--accent)">Calibration Results</h4>
            <div class="petro-stat"><span>Matched Points</span><strong>${data.n_matched}</strong></div>
            <div class="petro-stat"><span>Equation</span><strong>${data.equation}</strong></div>
            <div class="petro-stat"><span>R²</span><strong>${data.r_squared}</strong></div>
            <div class="petro-stat"><span>RMSE</span><strong>${data.rmse}</strong></div>
            <div class="petro-stat"><span>Slope</span><strong>${data.slope}</strong></div>
            <div class="petro-stat"><span>Intercept</span><strong>${data.intercept}</strong></div>
        </div>`;

        if (data.permeability) {
            html += `<div class="stats-card" style="margin-bottom:16px">
                <h4 style="color:var(--accent)">Permeability Transform</h4>
                <div class="petro-stat"><span>Equation</span><strong>${data.permeability.equation}</strong></div>
                <div class="petro-stat"><span>R²</span><strong>${data.permeability.r_squared}</strong></div>
                <div class="petro-stat"><span>Points</span><strong>${data.permeability.n_points}</strong></div>
            </div>`;
        }

        // Cross-plot: core vs log
        html += '<div><canvas id="coreCalCanvas" style="width:100%;height:300px;background:var(--bg-primary);border-radius:8px"></canvas></div>';

        container.innerHTML = html;
        container.className = '';
        container.style.padding = '0';

        // Render scatter
        setTimeout(() => {
            const canvas = document.getElementById('coreCalCanvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const W = canvas.parentElement.getBoundingClientRect().width;
            canvas.width = W * 2;
            canvas.height = 600;
            ctx.scale(2, 2);
            const H = 300;
            const pad = { top: 30, right: 30, bottom: 50, left: 60 };
            const pw = W - pad.left - pad.right;
            const ph = H - pad.top - pad.bottom;

            ctx.fillStyle = '#0a0e14';
            ctx.fillRect(0, 0, W, H);

            const xMin = Math.min(...data.matched_log) * 0.9;
            const xMax = Math.max(...data.matched_log) * 1.1;
            const yMin = Math.min(...data.matched_core) * 0.9;
            const yMax = Math.max(...data.matched_core) * 1.1;

            // Grid
            ctx.strokeStyle = 'rgba(42,52,70,0.5)';
            ctx.lineWidth = 0.5;
            for (let i = 0; i <= 4; i++) {
                ctx.beginPath();
                ctx.moveTo(pad.left + pw/4*i, pad.top);
                ctx.lineTo(pad.left + pw/4*i, pad.top + ph);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(pad.left, pad.top + ph/4*i);
                ctx.lineTo(pad.left + pw, pad.top + ph/4*i);
                ctx.stroke();
            }

            // Points
            ctx.fillStyle = '#d4a853';
            data.matched_log.forEach((x, i) => {
                const px = pad.left + ((x - xMin) / (xMax - xMin)) * pw;
                const py = pad.top + ((yMax - data.matched_core[i]) / (yMax - yMin)) * ph;
                ctx.beginPath();
                ctx.arc(px, py, 5, 0, Math.PI * 2);
                ctx.fill();
            });

            // 1:1 line
            ctx.strokeStyle = 'rgba(255,255,255,0.2)';
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(pad.left, pad.top + ph);
            ctx.lineTo(pad.left + pw, pad.top);
            ctx.stroke();
            ctx.setLineDash([]);

            // Labels
            ctx.fillStyle = '#9aa8b8';
            ctx.font = '12px Geologica';
            ctx.textAlign = 'center';
            ctx.fillText(`Log ${curve}`, pad.left + pw/2, H - 10);
            ctx.save();
            ctx.translate(16, pad.top + ph/2);
            ctx.rotate(-Math.PI/2);
            ctx.fillText('Core Porosity', 0, 0);
            ctx.restore();

            // R² label
            ctx.fillStyle = '#d4a853';
            ctx.font = '14px Geologica';
            ctx.textAlign = 'left';
            ctx.fillText(`R² = ${data.r_squared}`, pad.left + 10, pad.top + 20);
        }, 100);
    }
,

    async runQcAutofix() {
        if (!this.currentWell) { GeoToast.warn('Select a well first'); return; }
        GeoLoading.show('Running enhanced QC...');
        try {
            const resp = await fetch(`/api/wells/${this.currentWell.id}/qc-autofix`, {
                method: 'POST', headers: { 'Content-Type': 'application/json', ...this._authHeaders() },
                body: JSON.stringify({})
            });
            const data = await resp.json();
            GeoLoading.hide();
            this._renderQcAutofix(data);
        } catch (e) {
            GeoLoading.hide();
            GeoToast.error('QC failed');
        }
    }
,

    _renderQcAutofix(data) {
        const container = document.getElementById('qcAutofixResults');
        if (!container) return;

        const gradeClass = data.grade === 'A' ? 'qc-grade-a' : data.grade === 'B' ? 'qc-grade-b' : 'qc-grade-c';

        let html = `<div style="display:flex;align-items:center;gap:20px;margin-bottom:20px">
            <div class="qc-grade ${gradeClass}" style="font-size:48px">${data.grade}</div>
            <div>
                <div style="font-size:24px;font-weight:700;color:var(--text-primary)">${data.score}/100</div>
                <div style="font-size:12px;color:var(--text-muted)">${data.total_curves} curves analyzed | ${data.critical} critical | ${data.warnings} warnings</div>
            </div>
        </div>`;

        if (data.issues.length === 0) {
            html += '<div style="color:var(--success);font-size:14px;padding:20px;text-align:center">✓ No issues found — data quality is excellent</div>';
        } else {
            html += '<h4 style="color:var(--text-primary);margin-bottom:10px">Issues Found</h4>';
            html += '<table class="petro-table"><tr><th>Curve</th><th>Type</th><th>Severity</th><th>Detail</th></tr>';
            data.issues.forEach(i => {
                const sevColor = i.severity === 'critical' ? 'var(--danger)' : i.severity === 'warning' ? 'var(--warning)' : 'var(--text-muted)';
                html += `<tr><td>${i.curve}</td><td>${i.type}</td><td style="color:${sevColor};font-weight:600">${i.severity}</td><td>${i.detail}</td></tr>`;
            });
            html += '</table>';

            if (data.fixes.length) {
                html += '<h4 style="color:var(--accent);margin:16px 0 10px">Recommended Fixes</h4>';
                html += '<table class="petro-table"><tr><th>Curve</th><th>Action</th><th>Detail</th></tr>';
                data.fixes.forEach(f => {
                    html += `<tr><td>${f.curve}</td><td style="color:var(--accent);font-weight:600">${f.action}</td><td>${f.detail}</td></tr>`;
                });
                html += '</table>';
            }
        }

        container.innerHTML = html;
        container.className = '';
        container.style.padding = '0';
    }
,

    async computeSwMultiEquation() {
        if (!this.currentWell?.id) { GeoToast.warn('Load a well first'); return; }
        const result = document.getElementById('petroResults');
        if (result) result.innerHTML = '<p style="color:#58a6ff">⏳ Computing multi-equation saturation...</p>';
        try {
            const a = parseFloat(document.getElementById('archA')?.value || '1');
            const m = parseFloat(document.getElementById('archM')?.value || '2');
            const n = parseFloat(document.getElementById('archN')?.value || '2');
            const rw = parseFloat(document.getElementById('archRw')?.value || '0.1');
            const resp = await this._api(`/wells/${this.currentWell.id}/compute-sw`, {
                method: 'POST',
                body: JSON.stringify({ rw, a, m, n })
            });
            if (result) {
                let html = '<h3 style="color:#58a6ff">Multi-Equation Saturation Results</h3>';
                html += '<div style="font-size:12px;color:#8b949e;margin:6px 0">' + (resp.depth?.length || 0) + ' points</div>';
                if (resp.equations_used) html += '<div style="margin:8px 0"><strong>Equations:</strong> ' + resp.equations_used.join(', ') + '</div>';
                html += '<table style="width:100%;font-size:11px;border-collapse:collapse;margin-top:10px">';
                html += '<tr style="border-bottom:1px solid #30363d"><th style="text-align:left;padding:4px">Model</th><th>Mean Sw</th><th>Median</th><th>Min</th><th>Max</th></tr>';
                for (const [key, vals] of Object.entries(resp)) {
                    if (key.startsWith('sw_') && Array.isArray(vals)) {
                        const valid = vals.filter(v => v != null && !isNaN(v));
                        if (valid.length > 0) {
                            const sorted = [...valid].sort((a,b) => a-b);
                            const mean = valid.reduce((s,v) => s+v, 0) / valid.length;
                            html += '<tr style="border-bottom:1px solid #21262d"><td style="padding:4px">' + key.replace('sw_','').toUpperCase() + '</td><td style="text-align:center">' + mean.toFixed(4) + '</td><td style="text-align:center">' + sorted[Math.floor(sorted.length/2)].toFixed(4) + '</td><td style="text-align:center">' + sorted[0].toFixed(4) + '</td><td style="text-align:center">' + sorted[sorted.length-1].toFixed(4) + '</td></tr>';
                        }
                    }
                }
                html += '</table>';
                if (resp.gas_detected !== undefined) html += '<div style="margin-top:6px;color:' + (resp.gas_detected ? '#f0883e' : '#8b949e') + '"><strong>Gas:</strong> ' + (resp.gas_detected ? '⚠️ YES' : 'No') + '</div>';
                result.innerHTML = html;
            }
            GeoToast.success('Multi-equation Sw computed');
        } catch(e) { if (result) result.innerHTML = '<p style="color:#f85149">Error: ' + e.message + '</p>'; GeoToast.error('Sw failed: ' + e.message); }
    }
,

    async runMultimineral() {
        if (!this.currentWell?.id) { GeoToast.warn('Load a well first'); return; }
        const result = document.getElementById('petroResults');
        if (result) result.innerHTML = '<p style="color:#58a6ff">⏳ Running mineral solver...</p>';
        try {
            const resp = await this._api(`/wells/${this.currentWell.id}/multimineral`, {
                method: 'POST', body: JSON.stringify({})
            });
            if (result) {
                let html = '<h3 style="color:#58a6ff">Multimineral Solver</h3>';
                html += '<table style="width:100%;font-size:11px;border-collapse:collapse;margin-top:10px">';
                html += '<tr style="border-bottom:1px solid #30363d"><th style="text-align:left;padding:4px">Mineral</th><th>Mean</th><th>Min</th><th>Max</th></tr>';
                for (const mineral of ['quartz','calcite','dolomite','clay','porosity']) {
                    if (resp[mineral]) {
                        const valid = resp[mineral].filter(v => v != null && !isNaN(v));
                        if (valid.length > 0) {
                            const mean = valid.reduce((s,v) => s+v, 0) / valid.length;
                            const sorted = [...valid].sort((a,b) => a-b);
                            html += '<tr style="border-bottom:1px solid #21262d"><td style="padding:4px">' + mineral + '</td><td style="text-align:center">' + (mean*100).toFixed(1) + '%</td><td style="text-align:center">' + (sorted[0]*100).toFixed(1) + '%</td><td style="text-align:center">' + (sorted[sorted.length-1]*100).toFixed(1) + '%</td></tr>';
                        }
                    }
                }
                html += '</table>';
                if (resp.rms_error !== undefined) html += '<div style="margin-top:8px"><strong>RMS Error:</strong> ' + resp.rms_error.toFixed(6) + '</div>';
                result.innerHTML = html;
            }
            GeoToast.success('Multimineral complete');
        } catch(e) { if (result) result.innerHTML = '<p style="color:#f85149">Error: ' + e.message + '</p>'; GeoToast.error('Multimineral failed: ' + e.message); }
    }
,

    async runPermeabilityMulti() {
        if (!this.currentWell?.id) { GeoToast.warn('Load a well first'); return; }
        const result = document.getElementById('petroResults');
        if (result) result.innerHTML = '<p style="color:#58a6ff">⏳ Computing multi-model permeability...</p>';
        try {
            const rw = parseFloat(document.getElementById('archRw')?.value || '0.1');
            const resp = await this._api(`/wells/${this.currentWell.id}/permeability-multi`, {
                method: 'POST', body: JSON.stringify({ rw })
            });
            if (result) {
                let html = '<h3 style="color:#58a6ff">Multi-Model Permeability</h3>';
                html += '<table style="width:100%;font-size:11px;border-collapse:collapse;margin-top:10px">';
                html += '<tr style="border-bottom:1px solid #30363d"><th style="text-align:left;padding:4px">Model</th><th>Mean (mD)</th><th>Median</th><th>Min</th><th>Max</th></tr>';
                for (const [model, vals] of Object.entries(resp)) {
                    if (model === 'depth' || model === 'swirr' || !Array.isArray(vals)) continue;
                    const valid = vals.filter(v => v != null && !isNaN(v) && v > 0);
                    if (valid.length > 0) {
                        const sorted = [...valid].sort((a,b) => a-b);
                        const mean = valid.reduce((s,v) => s+v, 0) / valid.length;
                        html += '<tr style="border-bottom:1px solid #21262d"><td style="padding:4px">' + model.toUpperCase() + '</td><td style="text-align:center">' + mean.toFixed(2) + '</td><td style="text-align:center">' + sorted[Math.floor(sorted.length/2)].toFixed(2) + '</td><td style="text-align:center">' + sorted[0].toFixed(4) + '</td><td style="text-align:center">' + sorted[sorted.length-1].toFixed(1) + '</td></tr>';
                    }
                }
                html += '</table>';
                result.innerHTML = html;
            }
            GeoToast.success('Multi-permeability computed');
        } catch(e) { if (result) result.innerHTML = '<p style="color:#f85149">Error: ' + e.message + '</p>'; GeoToast.error('Multi-perm failed: ' + e.message); }
    }
,

    async runVclEnhanced() {
        if (!this.currentWell?.id) { GeoToast.warn('Load a well first'); return; }
        const result = document.getElementById('petroResults');
        if (result) result.innerHTML = '<p style="color:#58a6ff">⏳ Computing enhanced Vclay...</p>';
        try {
            const resp = await this._api(`/wells/${this.currentWell.id}/vcl-enhanced`, {
                method: 'POST', body: JSON.stringify({})
            });
            if (result) {
                let html = '<h3 style="color:#58a6ff">VClay QC (5 Methods)</h3>';
                html += '<table style="width:100%;font-size:11px;border-collapse:collapse;margin-top:10px">';
                html += '<tr style="border-bottom:1px solid #30363d"><th style="text-align:left;padding:4px">Method</th><th>Mean</th><th>Median</th><th>Std</th></tr>';
                for (const [method, vals] of Object.entries(resp)) {
                    if (method === 'depth' || !Array.isArray(vals)) continue;
                    const valid = vals.filter(v => v != null && !isNaN(v));
                    if (valid.length > 0) {
                        const mean = valid.reduce((s,v) => s+v, 0) / valid.length;
                        const sorted = [...valid].sort((a,b) => a-b);
                        const variance = valid.reduce((s,v) => s + (v-mean)**2, 0) / valid.length;
                        html += '<tr style="border-bottom:1px solid #21262d"><td style="padding:4px">' + method.replace('vcl_','').toUpperCase() + '</td><td style="text-align:center">' + mean.toFixed(4) + '</td><td style="text-align:center">' + sorted[Math.floor(sorted.length/2)].toFixed(4) + '</td><td style="text-align:center">' + Math.sqrt(variance).toFixed(4) + '</td></tr>';
                    }
                }
                html += '</table>';
                result.innerHTML = html;
            }
            GeoToast.success('VClay QC complete');
        } catch(e) { if (result) result.innerHTML = '<p style="color:#f85149">Error: ' + e.message + '</p>'; GeoToast.error('VClay QC failed: ' + e.message); }
    }
,

    async downloadRockSourceReport() {
        if (!this.currentWell?.id) return GeoToast.warn('Load a well first.');
        try {
            const blob = await this._apiBlob(`/wells/${this.currentWell.id}/report/rock-source.pdf`);
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${this.currentWell.name || 'well'}_rock_source_report.pdf`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            GeoToast.success('Rock/source report downloaded');
        } catch (e) {
            GeoToast.error('Report failed: ' + e.message);
        }
    },

    async runSourceRock() {
        if (!this.currentWell) return;
        const methodValue = document.getElementById('sourceRockMethod')?.value || 'passey_sonic';
        const method = methodValue.startsWith('schmoker') ? 'schmoker' : 'passey';
        const porosityMode = methodValue.endsWith('_density') ? 'density' : 'sonic';
        const num = (id, fallback) => {
            const value = Number(document.getElementById(id)?.value);
            return Number.isFinite(value) ? value : fallback;
        };
        GeoLoading.show('Computing source-rock TOC...');
        try {
            const result = await this._api(`/wells/${this.currentWell.id}/source-rock`, {
                method: 'POST',
                body: JSON.stringify({
                    method,
                    porosity_mode: porosityMode,
                    lom: num('sourceRockLom', 10),
                    toc_base: num('sourceRockTocBase', 0),
                }),
            });
            const toc = result.stats?.toc || {};
            const vker = result.stats?.vker || {};
            const fmt = (v, digits = 2) => Number(v ?? 0).toFixed(digits);
            const host = document.getElementById('sourceRockResults');
            if (host) {
                host.innerHTML = `
                    <div><span style="color:#8b949e">TOC:</span> mean ${fmt(toc.mean)} wt%, max ${fmt(toc.max)} wt%</div>
                    <div><span style="color:#8b949e">Kerogen:</span> mean ${fmt(vker.mean, 3)} v/v</div>
                    <div><span style="color:#8b949e">Curves:</span> ${escapeHtml(result.curves?.toc || 'TOC')}, ${escapeHtml(result.curves?.vker || 'VKER')}</div>
                    ${(result.warnings || []).map(w => `<div style="color:#d29922">${escapeHtml(String(w))}</div>`).join('')}`;
            }
            GeoToast.success('TOC and VKER curves added');
            await this._loadCurveData();
        } catch (e) {
            GeoToast.error('Source rock failed: ' + e.message);
        } finally {
            GeoLoading.hide();
        }
    },

    async runDualWater() {
        if (!this.currentWell?.id) { GeoToast.warn('Load a well first'); return; }
        const result = document.getElementById('petroResults');
        if (result) result.innerHTML = '<p style="color:#58a6ff">⏳ Running Dual-Water model...</p>';
        try {
            const rw = parseFloat(document.getElementById('archRw')?.value || '0.1');
            const resp = await this._api(`/wells/${this.currentWell.id}/dual-water`, {
                method: 'POST', body: JSON.stringify({ rw })
            });
            if (result) {
                let html = '<h3 style="color:#58a6ff">Dual-Water Model</h3>';
                const sw = resp.sw_dual_water || resp.sw || [];
                const valid = sw.filter(v => v != null && !isNaN(v));
                if (valid.length > 0) {
                    const mean = valid.reduce((s,v) => s+v, 0) / valid.length;
                    html += '<div style="margin:8px 0"><strong>Mean Sw:</strong> ' + mean.toFixed(4) + ' (' + valid.length + ' pts)</div>';
                }
                result.innerHTML = html;
            }
            GeoToast.success('Dual-Water complete');
        } catch(e) { if (result) result.innerHTML = '<p style="color:#f85149">Error: ' + e.message + '</p>'; GeoToast.error('Dual-Water failed: ' + e.message); }
    }
,

    async runStratNormalize() {
        if (!this.currentWell?.id) { GeoToast.warn('Load a well first'); return; }
        // Get first formation top as reference, or ask user
        try {
            const tops = await this._api(`/wells/${this.currentWell.id}/tops`);
            if (!tops || tops.length === 0) { GeoToast.warn('Add formation tops first for strat normalization'); return; }
            const refFormation = tops[0].formation_name || tops[0].name;
            await this._api(`/wells/${this.currentWell.id}/strat-normalize`, {
                method: 'POST', body: JSON.stringify({ reference_formation: refFormation })
            });
            GeoToast.success('Strat normalization complete (ref: ' + refFormation + ')');
        } catch(e) { GeoToast.error('Strat normalize failed: ' + e.message); }
    }
,
});
