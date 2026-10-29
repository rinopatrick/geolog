/**
 * Reports, dashboard, admin, session and export methods for GeoLogApp.
 * Loaded after app.js and before bootstrap.js.
 */
Object.assign(GeoLogApp.prototype, {
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
    },

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
    },

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
            this._showOpenDownloadsCTA('Export package downloaded');
        } catch (e) {
            GeoToast.error('Export failed: ' + e.message);
        }
    },

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
    },

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
    },

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
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#c9d1d9">${escapeHtml(w.name || '-')}</td>`;
                    html += `<td style="padding:4px 6px;border:1px solid #21262d;color:#8b949e">${escapeHtml(w.uwi || '-')}</td>`;
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
    },

    async loadFormationMatrix() {
        if (!this.projects?.[0]) return;
        const pid = this.projects[0].id;
        try {
            const data = await this._api(`/projects/${pid}/formation-matrix`);
            let html = '<div style="overflow:auto"><table style="border-collapse:collapse;font-size:12px">';
            html += '<thead><tr style="background:#161b22">';
            html += '<th style="padding:6px 12px;border:1px solid #30363d;color:#58a6ff;text-align:left">Formation</th>';
            for (const w of data.wells) {
                html += `<th style="padding:6px 12px;border:1px solid #30363d;color:#58a6ff;text-align:center">${escapeHtml(w.name)}</th>`;
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
    },

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
        GeoLoading.show('Running batch petrophysics...');
        try {
            const result = await this._api(`/projects/${pid}/batch-petro`, {
                method: 'POST', body: JSON.stringify(params)
            });
            document.getElementById('batchResults').innerHTML = `
                <div style="background:#161b22;border:1px solid #3fb95033;border-radius:8px;padding:12px;margin-top:8px">
                    <strong style="color:#3fb950">✓ Applied to ${result.updated} wells</strong><br>
                    <span style="color:#c9d1d9">${escapeHtml(result.wells.join(', '))}</span>
                </div>`;
            GeoToast.success(`Parameters applied to ${result.updated} wells`);
        } catch (e) { GeoToast.error(e.message); }
        finally { GeoLoading.hide(); }
    },

    async runBatchPetroAsync() {
        if (!this.projects?.[0]) return GeoToast.warn('No active project');
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
        GeoLoading.show('Queueing batch petrophysics job...');
        try {
            const res = await this._api(`/projects/${pid}/batch-petro-async`, {
                method: 'POST', body: JSON.stringify(params)
            });
            this._trackJob(res.job_id);
            GeoToast.success('Batch petro job queued: ' + res.job_id);
        } catch (e) { GeoToast.error('Queue failed: ' + e.message); }
        finally { GeoLoading.hide(); }
    },

    _trackJob(jobId) {
        if (!jobId) return;
        if (!this.jobIds.includes(jobId)) {
            this.jobIds.unshift(jobId);
            this.jobIds = this.jobIds.slice(0, 20);
            localStorage.setItem('geolog_job_ids', JSON.stringify(this.jobIds));
        }
        this.refreshJobs();
    },

    async refreshJobs() {
        const host = document.getElementById('jobMonitorList');
        if (!host) return;
        if (!this.jobIds.length) {
            host.innerHTML = '<p style="color:#8b949e">No jobs yet.</p>';
            return;
        }
        let html = '';
        for (const id of this.jobIds) {
            try {
                const j = await this._api(`/jobs/${id}`);
                const color = j.status === 'done' ? '#3fb950' : j.status === 'failed' ? '#f85149' : '#d29922';
                html += `<div style="border:1px solid #30363d;border-radius:6px;padding:8px;margin-bottom:6px">`;
                html += `<div><strong>${j.type}</strong> <span style="color:${color}">${j.status}</span></div>`;
                html += `<div style="font-size:11px;color:#8b949e">${j.id}</div>`;
                html += `</div>`;
            } catch (_) { }
        }
        host.innerHTML = html || '<p style="color:#8b949e">No readable jobs.</p>';
    },

    _showFirstRunWelcome() {
        if (localStorage.getItem('geolog_welcome_seen')) return;
        setTimeout(() => {
            GeoToast.info('Welcome to GeoLog! Upload a LAS file to begin. Press ? for keyboard shortcuts.', 7000);
            localStorage.setItem('geolog_welcome_seen', '1');
        }, 1200);
    },

    async loadAuditLog() {
        if (!this.projects.length) return [];
        const pid = this.projects[0]?.id;
        try {
            const resp = await fetch(`/api/audit-log?project_id=${pid}&limit=50`, { headers: this._authHeaders() });
            return await resp.json();
        } catch { return []; }
    },

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
    },

    async loadCrossPlotMatrix() {
        if (!this.projects.length) return;
        const pid = this.projects[0]?.id;
        const curveX = document.getElementById('matrixCurveX')?.value || 'GR';
        const curveY = document.getElementById('matrixCurveY')?.value || 'RT';
        try {
            const resp = await fetch(`/api/projects/${pid}/crossplot-matrix?curve_x=${curveX}&curve_y=${curveY}`, { headers: this._authHeaders() });
            const data = await resp.json();
            this._renderMatrixPlot(data);
        } catch (e) {
            GeoToast.error('Failed to load matrix data');
        }
    },

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
    },

    async exportReport() {
        if (!this.currentWell) { GeoToast.warn('Select a well first'); return; }
        GeoLoading.show('Generating report...');
        try {
            const resp = await fetch(`/api/wells/${this.currentWell.id}/report`, { headers: this._authHeaders() });
            const data = await resp.json();
            GeoLoading.hide();
            this._renderReportPreview(data);
        } catch (e) {
            GeoLoading.hide();
            GeoToast.error('Report generation failed');
        }
    },

    _renderReportPreview(data) {
        const w = data.well || {};
        let html = `<div class="report-preview">
            <h1>Well Log Report — ${escapeHtml(w.name || 'Unknown')}</h1>
            <p><strong>UWI:</strong> ${escapeHtml(w.uwi || '—')} | <strong>Operator:</strong> ${escapeHtml(w.operator || '—')} | <strong>Field:</strong> ${escapeHtml(w.field_name || '—')} | <strong>Generated:</strong> ${escapeHtml(data.generated_at || '—')}</p>`;
        if (data.formation_tops && data.formation_tops.length) {
            html += `<h2>Formation Tops</h2><table><tr><th>Formation</th><th>Depth (${w.depth_unit || 'FT'})</th><th>Lithology</th></tr>`;
            data.formation_tops.forEach(t => {
                html += `<tr><td>${escapeHtml(t.formation_name)}</td><td>${t.depth?.toFixed(1) || '—'}</td><td>${escapeHtml(t.lithology || '—')}</td></tr>`;
            });
            html += '</table>';
        }
        if (data.zones && data.zones.length) {
            html += `<h2>Zones</h2><table><tr><th>Zone</th><th>Top</th><th>Bottom</th><th>Gross (ft)</th></tr>`;
            data.zones.forEach(z => {
                html += `<tr><td>${escapeHtml(z.name)}</td><td>${z.top_depth?.toFixed(1)}</td><td>${z.bottom_depth?.toFixed(1)}</td><td>${(z.bottom_depth - z.top_depth)?.toFixed(1)}</td></tr>`;
            });
            html += '</table>';
        }
        if (data.curve_summary && data.curve_summary.length) {
            html += `<h2>Curve Summary</h2><table><tr><th>Run</th><th>Curve</th><th>Unit</th><th>Count</th><th>Min</th><th>Max</th><th>Mean</th></tr>`;
            data.curve_summary.forEach(c => {
                html += `<tr><td>${c.run}</td><td>${escapeHtml(c.mnemonic)}</td><td>${escapeHtml(c.unit || '')}</td><td>${c.count?.toLocaleString()}</td><td>${c.min?.toFixed(3) || '—'}</td><td>${c.max?.toFixed(3) || '—'}</td><td>${c.mean?.toFixed(3) || '—'}</td></tr>`;
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
    },

    async loadUsers() {
        try {
            const users = await this._api('/users');
            this._renderUsers(users || []);
        } catch { }
    },

    _renderUsers(users) {
        const container = document.getElementById('usersResults');
        if (!container) return;

        if (!users.length) {
            container.innerHTML = `<div class="empty-state">
                <div class="empty-state-icon"><i data-lucide="users"></i></div>
                <h3>No Users</h3>
                <p>Add users to manage access and track who makes changes.</p>
            </div>`;
            if (typeof lucide !== 'undefined') lucide.createIcons({ attrs: { 'stroke-width': 1.5 } });
            return;
        }

        const roleColors = { admin: 'var(--danger)', interpreter: 'var(--accent)', viewer: 'var(--text-muted)' };
        let html = '<table class="petro-table"><tr><th>Username</th><th>Display Name</th><th>Role</th><th>Created</th><th>Actions</th></tr>';
        users.forEach(u => {
            html += `<tr>
                <td style="font-weight:600">${u.username}</td>
                <td>${u.display_name || '—'}</td>
                <td style="color:${roleColors[u.role] || 'var(--text-muted)'};font-weight:600">${u.role}</td>
                <td style="font-size:10px">${new Date(u.created_at).toLocaleDateString()}</td>
                <td><button class="btn-sm" data-action="app.deleteUser" data-args='[${u.id}]'><i data-lucide="trash-2"></i></button></td>
            </tr>`;
        });
        html += '</table>';
        container.innerHTML = html;
        if (typeof lucide !== 'undefined') lucide.createIcons({ attrs: { 'stroke-width': 1.5 } });
    },

    createUser() {
        GeoModal.show({
            title: 'Add User',
            fields: [
                { id: 'username', label: 'Username', type: 'text', placeholder: 'jsmith' },
                { id: 'display_name', label: 'Display Name', type: 'text', placeholder: 'John Smith' },
                { id: 'role', label: 'Role', type: 'select', value: 'interpreter', options: [
                    { value: 'admin', label: 'Admin' },
                    { value: 'interpreter', label: 'Interpreter' },
                    { value: 'viewer', label: 'Viewer' },
                ]},
            ],
            onConfirm: async (vals) => {
                try {
                    await this._api('/users', { method: 'POST', body: JSON.stringify(vals) });
                    GeoToast.success('User created');
                    this.loadUsers();
                } catch (e) { GeoToast.error('Failed to create user: ' + e.message); }
            }
        });
    },

    loginWithToken() {
        GeoModal.show({
            title: 'JWT Bearer Authentication',
            fields: [
                { id: 'username', label: 'Username', type: 'text', value: 'admin' },
                { id: 'userToken', label: 'User Token / Secret', type: 'password', placeholder: 'Secret user token from backend/user' },
                { id: 'rawJwt', label: 'Or Paste Raw Bearer JWT', type: 'textarea', placeholder: 'eyJhbGci...' },
            ],
            onConfirm: async (vals) => {
                const rawJwt = (vals.rawJwt || '').trim();
                if (rawJwt) {
                    this.setAuthToken(rawJwt);
                    GeoToast.success('Stored custom Bearer JWT token');
                    return;
                }
                const username = (vals.username || '').trim();
                const token = (vals.userToken || '').trim();
                if (!username) {
                    GeoToast.error('Username required');
                    return;
                }
                try {
                    const res = await this._api('/users/token', {
                        method: 'POST',
                        body: JSON.stringify({ username, token }),
                    });
                    if (res && res.access_token) {
                        this.setAuthToken(res.access_token);
                        if (res.role) this.setActiveRole(res.role);
                        GeoToast.success(`Authenticated as ${res.username} (${res.role})`);
                    } else {
                        GeoToast.error('Login failed to return token');
                    }
                } catch (err) {
                    GeoToast.error('Login failed: ' + err.message);
                }
            }
        });
    },

    async deleteUser(uid) {
        if (!confirm('Delete this user?')) return;
        try {
            await this._api(`/users/${uid}`, { method: 'DELETE' });
            GeoToast.success('User deleted');
            this.loadUsers();
        } catch (e) {
            GeoToast.error('Failed to delete user: ' + e.message);
        }
    },

    _showOpenDownloadsCTA(message = 'Download complete') {
        GeoToast.showAction(message, 'Open Downloads', () => {
            const tab = window.open('chrome://downloads/', '_blank');
            if (!tab) {
                GeoToast.info('Open your browser Downloads (Ctrl+J)');
            }
        }, 'success', 8000);
    },

    async downloadReportPDF() {
        if (!this.currentWell?.id) { GeoToast.warn('Load a well first'); return; }
        try {
            const template = document.getElementById('pdfTemplate')?.value || 'professional';
            const includeCurves = !!document.getElementById('pdfIncludeCurves')?.checked;
            const includeQc = !!document.getElementById('pdfIncludeQc')?.checked;
            const qs = new URLSearchParams({
                template,
                include_curve_summary: includeCurves ? 'true' : 'false',
                include_qc: includeQc ? 'true' : 'false',
            });
            const resp = await fetch(`/api/wells/${this.currentWell.id}/report-pdf?${qs.toString()}`, { headers: this._authHeaders() });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = (this.currentWell.name || 'well') + '_report.pdf';
            document.body.appendChild(a); a.click(); document.body.removeChild(a);
            URL.revokeObjectURL(url);
            this._showOpenDownloadsCTA('PDF downloaded');
        } catch(e) { GeoToast.error('PDF failed: ' + e.message); }
    },

    async downloadReportPdf() { return this.downloadReportPDF(); },

    async saveSession() {
        if (!this.currentWell?.id) { GeoToast.warn('Load a well first'); return; }
        const session = {
            version: 1,
            timestamp: new Date().toISOString(),
            wellId: this.currentWell.id,
            wellName: this.currentWell.name,
            view: {
                start: this.renderer?.viewStart,
                stop: this.renderer?.viewStop,
                scale: this.renderer?.scale
            },
            params: {},
            tracks: this.renderer?.tracks?.map(t => ({name: t.name, curves: t.curves, width: t.width})),
            lastView: localStorage.getItem('geolog_last_view')
        };
        // Save petro params
        try {
            const resp = await this._api(`/wells/${this.currentWell.id}/petro-params`);
            session.params = resp;
        } catch(e) {}
        // Save to localStorage + download
        const key = `geolog_session_${this.currentWell.id}`;
        localStorage.setItem(key, JSON.stringify(session));
        // Download as file
        const blob = new Blob([JSON.stringify(session, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `${this.currentWell.name}_session.json`;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
        GeoToast.success('Session saved & downloaded');
    },

    async loadSession() {
        const input = document.createElement('input');
        input.type = 'file'; input.accept = '.json';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            try {
                const text = await file.text();
                const session = JSON.parse(text);
                // Restore well
                if (session.wellId) {
                    await this.selectWell(session.wellId);
                    // Restore view
                    if (session.view?.start && this.renderer) {
                        this.renderer.setView(session.view.start, session.view.stop);
                    }
                    // Restore params
                    if (session.params && Object.keys(session.params).length > 0) {
                        await this._api(`/wells/${session.wellId}/petro-params`, {
                            method: 'POST', body: JSON.stringify(session.params)
                        });
                    }
                }
                GeoToast.success('Session restored: ' + (session.wellName || 'unknown'));
            } catch(err) {
                GeoToast.error('Invalid session file: ' + err.message);
            }
        };
        input.click();
    },

    async batchExportAll() {
        const wells = this.wells || [];
        if (wells.length === 0) { GeoToast.warn('No wells to export'); return; }
        GeoToast.info('Exporting ' + wells.length + ' wells...');
        try {
            // Use the first project
            const projects = await this._api('/projects/');
            if (!projects.length) { GeoToast.warn('No project found'); return; }
            const pid = projects[0].id;
            const resp = await fetch(`/api/projects/${pid}/tops-export`, { headers: this._authHeaders() });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'all_wells_export.csv';
            document.body.appendChild(a); a.click(); document.body.removeChild(a);
            URL.revokeObjectURL(url);
            // Also export each well LAS
            for (const w of wells) {
                try {
                    const lasResp = await fetch(`/api/wells/${w.id}/export-las`, { headers: this._authHeaders() });
                    if (lasResp.ok) {
                        const lasBlob = await lasResp.blob();
                        const lasUrl = URL.createObjectURL(lasBlob);
                        const la = document.createElement('a');
                        la.href = lasUrl; la.download = `${w.name}.las`;
                        document.body.appendChild(la); la.click(); document.body.removeChild(la);
                        URL.revokeObjectURL(lasUrl);
                    }
                } catch(e) {}
            }
            this._showOpenDownloadsCTA('Batch export complete: ' + wells.length + ' wells');
        } catch(e) {
            GeoToast.error('Batch export failed: ' + e.message);
        }
    },

    toggleTheme() {
        this._currentTheme = this._currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', this._currentTheme);
        localStorage.setItem('geolog_theme', this._currentTheme);
        if (this._currentTheme === 'light') {
            document.documentElement.style.setProperty('--bg-primary', '#ffffff');
            document.documentElement.style.setProperty('--bg-secondary', '#f6f8fa');
            document.documentElement.style.setProperty('--bg-tertiary', '#eaeef2');
            document.documentElement.style.setProperty('--text-primary', '#1f2328');
            document.documentElement.style.setProperty('--text-secondary', '#656d76');
            document.documentElement.style.setProperty('--border', '#d0d7de');
            document.body.style.background = '#ffffff';
            document.body.style.color = '#1f2328';
        } else {
            document.documentElement.style.setProperty('--bg-primary', '#0d1117');
            document.documentElement.style.setProperty('--bg-secondary', '#161b22');
            document.documentElement.style.setProperty('--bg-tertiary', '#21262d');
            document.documentElement.style.setProperty('--text-primary', '#e6edf3');
            document.documentElement.style.setProperty('--text-secondary', '#8b949e');
            document.documentElement.style.setProperty('--border', '#30363d');
            document.body.style.background = '';
            document.body.style.color = '';
        }
        // Update renderer colors
        if (this.renderer) {
            const isLight = this._currentTheme === 'light';
            this.renderer.colors.bg = isLight ? '#ffffff' : '#0d1117';
            this.renderer.colors.headerBg = isLight ? '#f6f8fa' : '#161b22';
            this.renderer.colors.trackBorder = isLight ? '#d0d7de' : '#30363d';
            this.renderer.colors.headerText = isLight ? '#1f2328' : '#e6edf3';
            this.renderer.colors.depthText = isLight ? '#656d76' : '#8b949e';
            this.renderer.colors.gridLine = isLight ? '#eaeef2' : '#1a1f25';
            this.renderer.colors.cursorLine = isLight ? '#0969da' : '#58a6ff';
            this.renderer.requestRender();
        }
        GeoToast.info('Theme: ' + this._currentTheme);
    },

    _exportSVG() {
        if (!this.renderer) { GeoToast.warn('Load a well first'); return; }
        const svg = this.renderer.exportSVG();
        const blob = new Blob([svg], {type: 'image/svg+xml'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = (this.currentWell?.name || 'log') + '_export.svg';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
        GeoToast.success('SVG exported');
    },

    async _exportClientBundle() {
        if (!this.currentWell) { GeoToast.warn('Select a well first'); return; }
        try {
            GeoLoading.show('Preparing client bundle...');
            const wid = this.currentWell.id;
            const blob = await this._apiBlob(`/wells/${wid}/export-bundle`);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${this.currentWell.name || 'well'}_bundle.zip`;
            a.click();
            URL.revokeObjectURL(url);
            GeoToast.info('Bundle downloaded');
        } catch (e) {
            GeoToast.error('Bundle export failed: ' + (e.message || e));
        } finally { GeoLoading.hide(); }
    },
});
