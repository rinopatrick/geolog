/**
 * Zonation + Net Pay Report Panel — standalone module for GeoLog.
 * Provides auto-zone computation, zone table rendering, and CSV/PDF export.
 */
/* exported ZoneReportPanel */

class ZoneReportPanel {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.apiBase = '/api/wells';
        this.lastResult = null;
    }

    render(wellId) {
        if (!this.container) return;
        this.wellId = wellId;
        this.container.innerHTML = `
        <div style="padding:16px">
            <h3 style="margin:0 0 12px;color:#e6edf9;font-size:16px">Zonation & Net Pay Report</h3>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-bottom:12px">
                <label style="font-size:12px;color:#8b949e">VSH Max
                    <input type="number" id="znCutVsh" value="0.35" step="0.05" min="0" max="1"
                        style="width:100%;background:#161b22;color:#e6edf9;border:1px solid #30363d;border-radius:4px;padding:4px 6px">
                </label>
                <label style="font-size:12px;color:#8b949e">PHIE Min
                    <input type="number" id="znCutPhie" value="0.10" step="0.05" min="0" max="1"
                        style="width:100%;background:#161b22;color:#e6edf9;border:1px solid #30363d;border-radius:4px;padding:4px 6px">
                </label>
                <label style="font-size:12px;color:#8b949e">SW Max
                    <input type="number" id="znCutSw" value="0.60" step="0.05" min="0" max="1"
                        style="width:100%;background:#161b22;color:#e6edf9;border:1px solid #30363d;border-radius:4px;padding:4px 6px">
                </label>
                <label style="font-size:12px;color:#8b949e">Gap Merge (ft)
                    <input type="number" id="znGapMerge" value="2.0" step="0.5" min="0" max="50"
                        style="width:100%;background:#161b22;color:#e6edf9;border:1px solid #30363d;border-radius:4px;padding:4px 6px">
                </label>
            </div>
            <div style="display:flex;gap:8px;margin-bottom:16px">
                <button id="znAutoZoneBtn" class="btn-primary" style="padding:6px 16px;border-radius:4px;border:none;cursor:pointer;background:#238636;color:white;font-size:13px">⚡ Auto-Zone</button>
                <button id="znExportCSV" style="padding:6px 12px;border-radius:4px;border:1px solid #30363d;background:transparent;color:#8b949e;cursor:pointer;font-size:12px;display:none">📄 Export CSV</button>
                <button id="znExportPDF" style="padding:6px 12px;border-radius:4px;border:1px solid #30363d;background:transparent;color:#8b949e;cursor:pointer;font-size:12px;display:none">📑 Export PDF</button>
            </div>
            <div id="znSummary" style="margin-bottom:12px"></div>
            <div id="znTable" style="overflow-x:auto"></div>
        </div>`;

        document.getElementById('znAutoZoneBtn').onclick = () => this._runAutoZone();
        document.getElementById('znExportCSV').onclick = () => this._downloadCSV();
        document.getElementById('znExportPDF').onclick = () => this._downloadPDF();
    }

    async _runAutoZone() {
        const btn = document.getElementById('znAutoZoneBtn');
        btn.disabled = true;
        btn.textContent = 'Computing...';
        try {
            const vsh_max = parseFloat(document.getElementById('znCutVsh').value) || 0.35;
            const phie_min = parseFloat(document.getElementById('znCutPhie').value) || 0.10;
            const sw_max = parseFloat(document.getElementById('znCutSw').value) || 0.60;
            const gap_merge_ft = parseFloat(document.getElementById('znGapMerge').value) || 2.0;

            const resp = await fetch(`${this.apiBase}/${this.wellId}/auto-zone`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-User-Role': (window.app?.currentRole || 'admin') },
                body: JSON.stringify({ vsh_max, phie_min, sw_max, gap_merge_ft }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${resp.status}`);
            }
            this.lastResult = await resp.json();
            this._renderSummary(this.lastResult.summary);
            this._renderTable(this.lastResult.zones);
            document.getElementById('znExportCSV').style.display = '';
            document.getElementById('znExportPDF').style.display = '';
            if (window.GeoToast) GeoToast.success(`Found ${this.lastResult.zones.length} zones`);
        } catch (e) {
            if (window.GeoToast) GeoToast.error('Auto-zone failed: ' + e.message);
            else alert('Auto-zone failed: ' + e.message);
        } finally {
            btn.disabled = false;
            btn.textContent = '⚡ Auto-Zone';
        }
    }

    _renderSummary(s) {
        const el = document.getElementById('znSummary');
        if (!s) { el.innerHTML = ''; return; }
        el.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin-bottom:12px">
            ${this._card('Zones', s.num_zones, '#58a6ff')}
            ${this._card('Gross', (s.total_gross_ft||0).toFixed(1)+' ft', '#8b949e')}
            ${this._card('Net Pay', (s.total_net_pay_ft||0).toFixed(1)+' ft', '#3fb950')}
            ${this._card('NTG', (s.overall_ntg||0).toFixed(2), '#d29922')}
            ${this._card('Avg PHIE', s.avg_phie!=null ? (s.avg_phie*100).toFixed(1)+'%' : '—', '#a371f7')}
            ${this._card('Avg SW', s.avg_sw!=null ? (s.avg_sw*100).toFixed(1)+'%' : '—', '#f85149')}
            ${this._card('Avg VSH', s.avg_vsh!=null ? (s.avg_vsh*100).toFixed(1)+'%' : '—', '#79c0ff')}
        </div>`;
    }

    _card(label, value, color) {
        return `<div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:8px 10px;text-align:center">
            <div style="font-size:11px;color:#8b949e;margin-bottom:4px">${label}</div>
            <div style="font-size:16px;font-weight:600;color:${color}">${value}</div>
        </div>`;
    }

    _renderTable(zones) {
        const el = document.getElementById('znTable');
        if (!zones || !zones.length) { el.innerHTML = '<div style="color:#8b949e;font-size:13px">No zones found with current cutoffs.</div>'; return; }
        const fmt = (v, d=1) => v != null ? v.toFixed(d) : '—';
        const pct = (v) => v != null ? (v*100).toFixed(1)+'%' : '—';
        let html = `<table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="border-bottom:2px solid #30363d;text-align:left">
            <th style="padding:6px 8px;color:#8b949e">Zone</th>
            <th style="padding:6px 8px;color:#8b949e">Top</th>
            <th style="padding:6px 8px;color:#8b949e">Base</th>
            <th style="padding:6px 8px;color:#8b949e;text-align:right">Gross</th>
            <th style="padding:6px 8px;color:#8b949e;text-align:right">Net Pay</th>
            <th style="padding:6px 8px;color:#8b949e;text-align:right">NTG</th>
            <th style="padding:6px 8px;color:#8b949e;text-align:right">Avg PHIE</th>
            <th style="padding:6px 8px;color:#8b949e;text-align:right">Avg SW</th>
            <th style="padding:6px 8px;color:#8b949e;text-align:right">Avg VSH</th>
        </tr></thead><tbody>`;
        for (const z of zones) {
            const color = z.ntg > 0.5 ? '#3fb950' : z.ntg > 0.2 ? '#d29922' : '#f85149';
            html += `<tr style="border-bottom:1px solid #21262d">
                <td style="padding:5px 8px"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>${z.name}</td>
                <td style="padding:5px 8px">${fmt(z.top_depth)}</td>
                <td style="padding:5px 8px">${fmt(z.bottom_depth)}</td>
                <td style="padding:5px 8px;text-align:right">${fmt(z.gross_ft)}</td>
                <td style="padding:5px 8px;text-align:right;color:${color};font-weight:600">${fmt(z.net_pay_ft)}</td>
                <td style="padding:5px 8px;text-align:right">${fmt(z.ntg, 2)}</td>
                <td style="padding:5px 8px;text-align:right">${pct(z.avg_phie)}</td>
                <td style="padding:5px 8px;text-align:right">${pct(z.avg_sw)}</td>
                <td style="padding:5px 8px;text-align:right">${pct(z.avg_vsh)}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        el.innerHTML = html;
    }

    _downloadCSV() {
        if (!this.lastResult) return;
        const rows = [['Zone','Top Depth','Base Depth','Gross (ft)','Net Pay (ft)','NTG','Avg PHIE','Avg SW','Avg VSH']];
        for (const z of this.lastResult.zones) {
            rows.push([z.name, z.top_depth, z.bottom_depth, z.gross_ft, z.net_pay_ft, z.ntg, z.avg_phie, z.avg_sw, z.avg_vsh]);
        }
        const csv = rows.map(r => r.join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `zone_report_well_${this.wellId}.csv`;
        a.click();
    }

    _downloadPDF() {
        window.open(`${this.apiBase}/${this.wellId}/zone-report/pdf`, '_blank');
    }
}

if (typeof window !== 'undefined') window.ZoneReportPanel = ZoneReportPanel;
