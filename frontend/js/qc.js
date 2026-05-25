class QualityScoreCard {
    constructor(curveName, quality) {
        this.curveName = curveName;
        this.quality = quality || { score: 0, completeness_score: 0, outlier_score: 0, range_score: 0 };
    }

    _scoreColor(score) {
        if (score >= 85) return '#3fb950';
        if (score >= 70) return '#d29922';
        return '#f85149';
    }

    render() {
        const score = Number(this.quality.score || 0);
        const pct = Math.max(0, Math.min(100, score));
        const color = this._scoreColor(score);
        return `
            <div class="qc-score-card" style="border:1px solid #30363d;border-radius:8px;padding:10px;background:#0d1117">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                    <strong>${this.curveName}</strong>
                    <span style="color:${color};font-weight:700">${pct.toFixed(1)}</span>
                </div>
                <div style="height:8px;background:#21262d;border-radius:6px;overflow:hidden">
                    <div style="height:100%;width:${pct}%;background:${color}"></div>
                </div>
                <div style="font-size:11px;color:#8b949e;margin-top:8px">
                    C:${(this.quality.completeness_score || 0).toFixed(1)} • O:${(this.quality.outlier_score || 0).toFixed(1)} • R:${(this.quality.range_score || 0).toFixed(1)}
                </div>
            </div>
        `;
    }
}

class MissingIntervalTable {
    constructor(intervals = []) {
        this.intervals = intervals;
    }

    render() {
        if (!this.intervals.length) return '<div style="color:#3fb950">No missing intervals detected.</div>';
        const rows = this.intervals.map(it => `
            <tr>
                <td>${it.curve || '-'}</td>
                <td>${Number(it.start_depth ?? 0).toFixed(2)}</td>
                <td>${Number(it.end_depth ?? 0).toFixed(2)}</td>
                <td>${Number(it.gap_length ?? 0).toFixed(2)}</td>
                <td>${it.num_points ?? 0}</td>
            </tr>
        `).join('');
        return `
            <div style="max-height:240px;overflow:auto">
                <table class="petro-table" style="width:100%">
                    <thead><tr><th>Curve</th><th>Start Depth</th><th>End Depth</th><th>Gap Length</th><th>Points</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    }
}

class EnvFlagBadges {
    constructor(envFlags = {}) {
        this.envFlags = envFlags;
    }

    _badge(label, severity = 'low', detail = '') {
        const map = { low: '#3fb950', medium: '#d29922', high: '#f85149' };
        const color = map[severity] || '#8b949e';
        return `<span style="display:inline-block;padding:4px 8px;border:1px solid ${color};color:${color};border-radius:999px;font-size:12px;margin:2px">${label}${detail ? `: ${detail}` : ''}</span>`;
    }

    render() {
        const items = [];
        const w = this.envFlags.washout;
        const m = this.envFlags.mud_invasion;
        const s = this.envFlags.tool_standoff;
        if (w) items.push(this._badge('Washout', w.severity, `${((w.fraction_over_bit || 0) * 100).toFixed(1)}% over bit`));
        if (m) items.push(this._badge('Mud invasion', m.severity, `${((m.separation_fraction || 0) * 100).toFixed(1)}% sep`));
        if (s) items.push(this._badge('Tool standoff', s.severity, `${((s.fraction || 0) * 100).toFixed(1)}%`));
        if (!items.length) items.push(this._badge('No environmental flags', 'low'));
        return `<div>${items.join('')}</div>`;
    }
}

class SpikeVisualization {
    constructor(renderer = null) {
        this.renderer = renderer;
    }

    apply(spikeData = {}) {
        if (!this.renderer || typeof this.renderer.setEditOverlay !== 'function') return;
        const curveName = Object.keys(spikeData || {}).find(k => (spikeData[k]?.points || []).length);
        if (!curveName) {
            this.renderer.setEditOverlay({ enabled: false, selected: [], edited: [], ghosts: [] });
            if (typeof this.renderer.render === 'function') this.renderer.render();
            return;
        }

        const points = spikeData[curveName].points || [];
        const selected = points.slice(0, 200).map(p => ({ x: null, y: null, depth: p.depth, value: p.value }));
        this.renderer.setEditOverlay({
            enabled: true,
            mnemonic: curveName,
            selected,
            edited: [],
            ghosts: []
        });
        if (typeof this.renderer.render === 'function') this.renderer.render();
    }
}

class AdvancedQCPanel {
    constructor({ apiBase = '/api', qcContentId = 'qcContent', renderer = null } = {}) {
        this.apiBase = apiBase;
        this.qcContentId = qcContentId;
        this.renderer = renderer;
        this.spikeViz = new SpikeVisualization(renderer);
    }

    async load(wellId) {
        const res = await fetch(`${this.apiBase}/wells/${wellId}/advanced-qc`, {
            headers: { 'X-User-Role': (window.app?.currentRole || 'admin') },
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        this.render(data);
        this.spikeViz.apply(data.spikes || {});
        return data;
    }

    render(data) {
        const panel = document.getElementById(this.qcContentId);
        if (!panel) return;

        const summary = data.summary || {};
        const curveStats = data.curve_stats || {};
        const cards = Object.entries(curveStats)
            .map(([mn, stat]) => new QualityScoreCard(mn, stat.quality).render())
            .join('');
        const missingTable = new MissingIntervalTable(data.missing_intervals || []).render();
        const envBadges = new EnvFlagBadges(data.env_flags || {}).render();

        panel.innerHTML = `
            <div class="petro-summary" style="margin-bottom:12px">
                <div class="petro-stat"><span>Overall Score:</span> <strong>${Number(summary.overall_score || 0).toFixed(1)}</strong></div>
                <div class="petro-stat"><span>Overall Rating:</span> <strong>${summary.overall_rating || '-'}</strong></div>
                <div class="petro-stat"><span>Curves:</span> <strong>${summary.curve_count || 0}</strong></div>
                <div class="petro-stat"><span>Total Missing Intervals:</span> <strong>${summary.total_missing_intervals || 0}</strong></div>
                <div class="petro-stat"><span>Total Spike Points:</span> <strong>${summary.total_spike_points || 0}</strong></div>
            </div>

            <h4 style="margin:8px 0">Environmental Flags</h4>
            ${envBadges}

            <h4 style="margin:12px 0 8px">Curve Quality Scores</h4>
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px">${cards || '<div>No curves</div>'}</div>

            <h4 style="margin:12px 0 8px">Missing Intervals</h4>
            ${missingTable}
        `;
    }
}

window.AdvancedQCPanel = AdvancedQCPanel;
window.QualityScoreCard = QualityScoreCard;
window.MissingIntervalTable = MissingIntervalTable;
window.SpikeVisualization = SpikeVisualization;
window.EnvFlagBadges = EnvFlagBadges;

