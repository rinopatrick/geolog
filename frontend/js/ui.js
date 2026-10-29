/**
 * GeoLog — Oil & Gas Well Log Viewer Application
 */

// ─── UI Utilities ────────────────────────────────────────────
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}
window.escapeHtml = escapeHtml;

// Shared by the standalone modules (qc.js, templates.js, units.js, ...).
// They load before app.js, so call this at request time, not at load time.
window.geologAuthHeaders = function () {
    const headers = { 'X-User-Role': (window.app?.currentRole || 'viewer') };
    const token = window.app?.authToken || localStorage.getItem('geolog_auth_token') || '';
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
};
const GeoModal = {
    _resolve: null,
    _confirmed: false,
    show({ title, fields, onConfirm }) {
        return new Promise(resolve => {
            this._resolve = resolve;
            this._confirmed = false;
            document.getElementById('modalTitle').textContent = title;
            const body = document.getElementById('modalBody');
            body.innerHTML = fields.map(f => {
                if (f.type === 'select') {
                    const opts = f.options.map(o => `<option value="${o.value}" ${o.value === f.value ? 'selected' : ''}>${o.label}</option>`).join('');
                    return `<label>${f.label}</label><select id="m_${f.id}">${opts}</select>`;
                }
                if (f.type === 'textarea') {
                    return `<label>${f.label}</label><textarea id="m_${f.id}" rows="${f.rows || 6}" style="width:100%;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:5px;padding:6px">${f.value ?? ''}</textarea>`;
                }
                return `<label>${f.label}</label><input id="m_${f.id}" type="${f.type || 'text'}" value="${f.value ?? ''}" placeholder="${f.placeholder || ''}"${f.step ? ` step="${f.step}"` : ''}${f.type === 'color' ? ' style="height:36px;padding:2px 4px"' : ''}>`;
            }).join('');
            const footer = document.getElementById('modalFooter');
            footer.innerHTML = `<button data-action="GeoModal.close">Cancel</button><button class="btn-primary" id="modalConfirm">OK</button>`;
            document.getElementById('modalConfirm').onclick = () => {
                const result = {};
                fields.forEach(f => { result[f.id] = document.getElementById(`m_${f.id}`).value; });
                this._confirmed = true;
                this._hide();
                if (onConfirm) onConfirm(result);
                resolve(result);
            };
            document.getElementById('modalOverlay').style.display = 'flex';
            setTimeout(() => { const first = body.querySelector('input, select'); if (first) first.focus(); }, 100);
        });
    },
    _hide() {
        document.getElementById('modalOverlay').style.display = 'none';
        this._resolve = null;
    },
    close() {
        if (this._resolve) { const r = this._resolve; this._resolve = null; r(null); }
        this._hide();
    }
};

const GeoToast = {
    show(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icons = { success: '✓', error: '✕', info: 'ℹ', warn: '⚠' };
        const icon = document.createElement('span');
        icon.textContent = icons[type] || '';
        const text = document.createElement('span');
        text.textContent = message;
        toast.appendChild(icon);
        toast.appendChild(text);
        container.appendChild(toast);
        setTimeout(() => { toast.classList.add('fade-out'); setTimeout(() => toast.remove(), 300); }, duration);
    },
    showAction(message, actionLabel, onAction, type = 'info', duration = 7000) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icons = { success: '✓', error: '✕', info: 'ℹ', warn: '⚠' };
        const icon = document.createElement('span');
        icon.textContent = icons[type] || '';
        const text = document.createElement('span');
        text.textContent = message;
        const btn = document.createElement('button');
        btn.className = 'btn-sm';
        btn.style.marginLeft = '8px';
        btn.textContent = actionLabel;
        btn.onclick = () => {
            try { onAction?.(); } catch {}
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        };
        toast.appendChild(icon);
        toast.appendChild(text);
        toast.appendChild(btn);
        container.appendChild(toast);
        setTimeout(() => { toast.classList.add('fade-out'); setTimeout(() => toast.remove(), 300); }, duration);
    },
    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 5000); },
    info(msg) { this.show(msg, 'info'); },
    warn(msg) { this.show(msg, 'warn', 4000); }
};

const GeoLoading = {
    show(text = 'Loading...') {
        document.getElementById('loadingText').textContent = text;
        document.getElementById('loadingOverlay').style.display = 'flex';
    },
    hide() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
};

// Expose the shared UI singletons to later scripts and delegated actions.
window.GeoModal = GeoModal;
window.GeoToast = GeoToast;
window.GeoLoading = GeoLoading;
