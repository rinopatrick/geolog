/**
 * Unit Normalization Panel — standalone module for GeoLog.
 * Shows unit mapping, conversion options, alias resolution.
 */
/* exported UnitNormalizationPanel */

class UnitNormalizationPanel {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.apiBase = '/api';
        this.unitMap = null;
    }

    render(wellId) {
        if (!this.container) return;
        this.wellId = wellId;
        this.container.innerHTML = `
        <div style="padding:16px">
            <h3 style="margin:0 0 12px;color:#e6edf9;font-size:16px">Unit Normalization</h3>
            <div style="display:flex;gap:8px;margin-bottom:16px">
                <button id="unitLoadBtn" style="padding:6px 16px;border-radius:4px;border:1px solid #30363d;background:transparent;color:#e6edf9;cursor:pointer;font-size:13px">📊 Load Unit Map</button>
                <button id="unitNormalizeBtn" class="btn-primary" style="padding:6px 16px;border-radius:4px;border:none;cursor:pointer;background:#238636;color:white;font-size:13px;display:none">⚙️ Normalize Units</button>
                <button id="unitAliasBtn" style="padding:6px 16px;border-radius:4px;border:1px solid #30363d;background:transparent;color:#d29922;cursor:pointer;font-size:13px;display:none">🔗 Resolve Aliases</button>
            </div>
            <div id="unitTable" style="overflow-x:auto"></div>
            <div id="unitAliasResult" style="margin-top:12px"></div>
        </div>`;

        document.getElementById('unitLoadBtn').onclick = () => this._loadUnitMap();
        document.getElementById('unitNormalizeBtn').onclick = () => this._normalizeUnits();
        document.getElementById('unitAliasBtn').onclick = () => this._resolveAliases();
    }

    async _loadUnitMap() {
        try {
            const resp = await fetch(`${this.apiBase}/wells/${this.wellId}/unit-map`, {
                headers: { 'X-User-Role': (window.app?.currentRole || 'admin') },
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            this.unitMap = await resp.json();
            this._renderUnitTable(this.unitMap.curves);
            document.getElementById('unitNormalizeBtn').style.display = '';
            document.getElementById('unitAliasBtn').style.display = '';
        } catch (e) {
            if (window.GeoToast) GeoToast.error('Failed to load unit map: ' + e.message);
        }
    }

    _renderUnitTable(curves) {
        const el = document.getElementById('unitTable');
        if (!curves || !curves.length) {
            el.innerHTML = '<div style="color:#8b949e;font-size:13px">No curves found.</div>';
            return;
        }

        const categoryColors = {
            resistivity: '#f85149', sonic: '#d29922', density: '#a371f7',
            porosity_pct: '#58a6ff', depth_ft_to_m: '#8b949e', unknown: '#484f58',
        };

        let html = `<table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="border-bottom:2px solid #30363d;text-align:left">
            <th style="padding:6px 8px;color:#8b949e">Mnemonic</th>
            <th style="padding:6px 8px;color:#8b949e">Unit</th>
            <th style="padding:6px 8px;color:#8b949e">Canonical</th>
            <th style="padding:6px 8px;color:#8b949e">Category</th>
            <th style="padding:6px 8px;color:#8b949e">Conversions</th>
        </tr></thead><tbody>`;

        for (const c of curves) {
            const color = categoryColors[c.category] || categoryColors.unknown;
            const convStr = (c.possible_conversions || []).map(
                cv => `→ ${cv.to_unit} (×${cv.factor})`
            ).join(', ') || '—';
            const aliasBadge = c.canonical !== c.mnemonic
                ? `<span style="background:#d2992230;color:#d29922;padding:1px 5px;border-radius:3px;font-size:10px;margin-left:4px">alias</span>`
                : '';
            html += `<tr style="border-bottom:1px solid #21262d">
                <td style="padding:5px 8px;font-weight:600">${c.mnemonic}${aliasBadge}</td>
                <td style="padding:5px 8px;color:#8b949e">${c.unit || '—'}</td>
                <td style="padding:5px 8px">${c.canonical}</td>
                <td style="padding:5px 8px"><span style="color:${color}">●</span> ${c.category}</td>
                <td style="padding:5px 8px;font-size:11px;color:#58a6ff">${convStr}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        el.innerHTML = html;
    }

    async _normalizeUnits() {
        try {
            const resp = await fetch(`${this.apiBase}/wells/${this.wellId}/normalize-units`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-User-Role': (window.app?.currentRole || 'admin') },
                body: JSON.stringify({ target: 'field' }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            if (window.GeoToast) GeoToast.info(`Unit analysis complete — ${result.conversions?.length || 0} conversion(s) available`);
            // Show conversion details
            if (result.conversions?.length) {
                const el = document.getElementById('unitTable');
                let note = '<div style="margin-top:12px;padding:10px;background:#161b22;border:1px solid #30363d;border-radius:6px;font-size:12px">';
                note += '<strong style="color:#d29922">Available Conversions:</strong><br>';
                for (const cv of result.conversions) {
                    note += `<div style="margin-top:4px">${cv.mnemonic}: ${cv.from_unit} → ${cv.to_unit} (factor: ${cv.factor}) — ${cv.action}</div>`;
                }
                note += '</div>';
                el.innerHTML += note;
            }
        } catch (e) {
            if (window.GeoToast) GeoToast.error('Normalization failed: ' + e.message);
        }
    }

    async _resolveAliases() {
        try {
            const resp = await fetch(`${this.apiBase}/wells/${this.wellId}/resolve-aliases`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-User-Role': (window.app?.currentRole || 'admin') },
                body: JSON.stringify({ auto: true }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            const el = document.getElementById('unitAliasResult');
            const aliases = (result.resolved || []).filter(r => r.is_alias);
            if (aliases.length === 0) {
                el.innerHTML = '<div style="color:#3fb950;font-size:13px">✓ All mnemonics are canonical — no aliases found.</div>';
            } else {
                let html = `<div style="padding:10px;background:#161b22;border:1px solid #d29922;border-radius:6px;font-size:12px">
                    <strong style="color:#d29922">Resolved ${aliases.length} alias(es):</strong>`;
                for (const a of aliases) {
                    html += `<div style="margin-top:3px">${a.original} → <strong>${a.canonical}</strong></div>`;
                }
                html += '</div>';
                el.innerHTML = html;
            }
            if (window.GeoToast) GeoToast.success(`Resolved ${result.alias_count} aliases`);
        } catch (e) {
            if (window.GeoToast) GeoToast.error('Alias resolution failed: ' + e.message);
        }
    }
}

if (typeof window !== 'undefined') window.UnitNormalizationPanel = UnitNormalizationPanel;
