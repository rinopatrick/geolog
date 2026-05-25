/**
 * Template Workflow Panel — standalone module for GeoLog.
 * Template cards, one-click apply, preview comparison.
 */
/* exported TemplateWorkflowPanel */

class TemplateWorkflowPanel {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.apiBase = '/api';
        this.templates = [];
    }

    async render(wellId) {
        if (!this.container) return;
        this.wellId = wellId;
        this.container.innerHTML = `
        <div style="padding:16px">
            <h3 style="margin:0 0 12px;color:#e6edf9;font-size:16px">Reservoir Template Workflow</h3>
            <div id="tmplCards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px"></div>
            <div id="tmplPreview" style="margin-top:16px"></div>
            <div id="tmplComparison" style="margin-top:16px"></div>
        </div>`;
        await this._loadTemplates();
        this._loadComparison();
    }

    async _loadTemplates() {
        try {
            const resp = await fetch(`${this.apiBase}/templates`, {
                headers: { 'X-User-Role': (window.app?.currentRole || 'admin') },
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            this.templates = data.templates || [];
            this._renderCards();
        } catch (e) {
            if (window.GeoToast) GeoToast.error('Failed to load templates: ' + e.message);
        }
    }

    _renderCards() {
        const el = document.getElementById('tmplCards');
        const typeColors = {
            clastic: '#58a6ff', carbonate: '#a371f7', unconventional: '#f85149',
        };
        el.innerHTML = this.templates.map(t => {
            const color = typeColors[t.reservoir_type] || '#8b949e';
            const p = t.params;
            const c = t.recommended_cutoffs;
            return `
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;cursor:pointer;transition:border-color .15s"
                 onmouseenter="this.style.borderColor='#58a6ff'" onmouseleave="this.style.borderColor='#30363d'"
                 onclick="window._tmplPanel?._previewTemplate('${t.name}')">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                    <span style="font-size:15px;font-weight:600;color:#e6edf9">${t.name}</span>
                    <span style="font-size:10px;padding:2px 6px;border-radius:3px;background:${color}22;color:${color}">${t.reservoir_type}</span>
                </div>
                <div style="font-size:11px;color:#8b949e;margin-bottom:10px">${t.description}</div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:11px">
                    <div><span style="color:#8b949e">Model:</span> <strong>${p.saturation_model}</strong></div>
                    <div><span style="color:#8b949e">Rw:</span> <strong>${p.rw}</strong></div>
                    <div><span style="color:#8b949e">a=${p.a}, m=${p.m}, n=${p.n}</span></div>
                    <div><span style="color:#8b949e">Rw:</span> <strong>${p.rw}</strong></div>
                </div>
                <div style="margin-top:8px;padding-top:8px;border-top:1px solid #21262d;font-size:11px">
                    <span style="color:#8b949e">Cutoffs:</span>
                    VSH&lt;${c.vsh_cutoff} | PHIE&gt;${c.phie_cutoff} | SW&lt;${c.sw_cutoff}
                </div>
                <div style="margin-top:8px;display:flex;gap:6px">
                    <button onclick="event.stopPropagation();window._tmplPanel?._applyTemplate('${t.name}')"
                        style="padding:4px 10px;border-radius:4px;border:none;background:#238636;color:white;font-size:11px;cursor:pointer">Apply</button>
                    <button onclick="event.stopPropagation();window._tmplPanel?._previewTemplate('${t.name}')"
                        style="padding:4px 10px;border-radius:4px;border:1px solid #30363d;background:transparent;color:#8b949e;font-size:11px;cursor:pointer">Preview</button>
                </div>
            </div>`;
        }).join('');
        window._tmplPanel = this;
    }

    async _previewTemplate(name) {
        try {
            const resp = await fetch(`${this.apiBase}/wells/${this.wellId}/template-preview`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-User-Role': (window.app?.currentRole || 'admin') },
                body: JSON.stringify({ template_name: name }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            this._renderPreview(result);
        } catch (e) {
            if (window.GeoToast) GeoToast.error('Preview failed: ' + e.message);
        }
    }

    _renderPreview(result) {
        const el = document.getElementById('tmplPreview');
        if (!result.changes || result.changes.length === 0) {
            el.innerHTML = `<div style="padding:12px;background:#161b22;border:1px solid #3fb950;border-radius:6px;color:#3fb950;font-size:13px">
                ✓ Well already matches <strong>${result.template}</strong> — no changes needed.</div>`;
            return;
        }

        let html = `<div style="padding:12px;background:#161b22;border:1px solid #30363d;border-radius:6px">
            <div style="font-size:14px;font-weight:600;color:#e6edf9;margin-bottom:8px">Preview: ${result.template}</div>
            <div style="font-size:12px;color:#8b949e;margin-bottom:10px">${result.description}</div>
            <table style="width:100%;border-collapse:collapse;font-size:12px">
            <thead><tr style="border-bottom:1px solid #30363d;text-align:left">
                <th style="padding:4px 8px;color:#8b949e">Parameter</th>
                <th style="padding:4px 8px;color:#8b949e">Current</th>
                <th style="padding:4px 8px;color:#8b949e">Template</th>
            </tr></thead><tbody>`;
        for (const c of result.changes) {
            html += `<tr style="border-bottom:1px solid #21262d">
                <td style="padding:4px 8px">${c.param}</td>
                <td style="padding:4px 8px;color:#f85149">${c.current ?? '—'}</td>
                <td style="padding:4px 8px;color:#3fb950">${c.proposed}</td>
            </tr>`;
        }
        html += `</tbody></table>
            <div style="margin-top:10px;display:flex;gap:8px">
                <button onclick="window._tmplPanel?._applyTemplate('${result.template}')"
                    style="padding:6px 16px;border-radius:4px;border:none;background:#238636;color:white;font-size:12px;cursor:pointer">✓ Apply Changes</button>
                <button onclick="document.getElementById('tmplPreview').innerHTML=''"
                    style="padding:6px 12px;border-radius:4px;border:1px solid #30363d;background:transparent;color:#8b949e;font-size:12px;cursor:pointer">Cancel</button>
            </div>
        </div>`;
        el.innerHTML = html;
    }

    async _applyTemplate(name) {
        try {
            const resp = await fetch(`${this.apiBase}/wells/${this.wellId}/apply-template`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-User-Role': (window.app?.currentRole || 'admin') },
                body: JSON.stringify({ template_name: name }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${resp.status}`);
            }
            const result = await resp.json();
            if (window.GeoToast) GeoToast.success(`Applied template: ${result.applied_template}`);
            document.getElementById('tmplPreview').innerHTML = '';
            this._loadComparison();
        } catch (e) {
            if (window.GeoToast) GeoToast.error('Apply failed: ' + e.message);
        }
    }

    async _loadComparison() {
        try {
            const resp = await fetch(`${this.apiBase}/wells/${this.wellId}/template-comparison`, {
                headers: { 'X-User-Role': (window.app?.currentRole || 'admin') },
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            this._renderComparison(result);
        } catch (e) {
            // Silent fail — comparison is optional
        }
    }

    _renderComparison(result) {
        const el = document.getElementById('tmplComparison');
        if (!result.comparisons || !result.comparisons.length) {
            el.innerHTML = '';
            return;
        }
        let html = `<div style="padding:12px;background:#161b22;border:1px solid #30363d;border-radius:6px">
            <div style="font-size:13px;font-weight:600;color:#e6edf9;margin-bottom:8px">Template Match Ranking</div>
            <div style="font-size:11px;color:#8b949e;margin-bottom:8px">Current: <strong>${result.current?.template || 'custom'}</strong></div>`;
        for (const c of result.comparisons) {
            const badge = c.is_current
                ? '<span style="background:#238636;color:white;padding:1px 6px;border-radius:3px;font-size:10px">current</span>'
                : `<span style="background:#21262d;color:#8b949e;padding:1px 6px;border-radius:3px;font-size:10px">${c.param_diffs} diff(s)</span>`;
            html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #21262d">
                <div>
                    <span style="font-size:12px;font-weight:500;color:#e6edf9">${c.name}</span>
                    <span style="font-size:10px;color:#8b949e;margin-left:8px">${c.reservoir_type}</span>
                </div>
                ${badge}
            </div>`;
        }
        html += '</div>';
        el.innerHTML = html;
    }
}

if (typeof window !== 'undefined') window.TemplateWorkflowPanel = TemplateWorkflowPanel;
