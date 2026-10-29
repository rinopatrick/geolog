/**
 * Saved report templates and custom PDF generation.
 * Loaded after app.js and before bootstrap.js.
 */
Object.assign(GeoLogApp.prototype, {
    _reportSections() {
        const mapping = [
            ['rbSectionRock', 'rock_source'],
            ['rbSectionZonation', 'zonation'],
            ['rbSectionProduction', 'production'],
            ['rbSectionQc', 'qc'],
            ['rbSectionCurves', 'curves'],
        ];
        return mapping.filter(([id]) => document.getElementById(id)?.checked).map(([, key]) => key);
    },

    async loadReportTemplates() {
        try {
            const templates = await this._api('/report-templates');
            this._reportTemplates = templates || [];
            const select = document.getElementById('reportTemplateSelect');
            if (select) {
                select.innerHTML = '<option value="">— inline selection —</option>' +
                    this._reportTemplates.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
            }
            const list = document.getElementById('reportTemplateList');
            if (list) {
                list.innerHTML = this._reportTemplates.length
                    ? this._reportTemplates.map(t => `<div style="padding:4px 0;border-bottom:1px solid #21262d"><strong>${escapeHtml(t.name)}</strong> · ${(t.config?.sections || []).map(escapeHtml).join(', ')}</div>`).join('')
                    : 'No saved templates.';
            }
        } catch (e) {
            GeoToast.error('Report templates: ' + e.message);
        }
    },

    applyReportTemplate(templateId) {
        const template = (this._reportTemplates || []).find(t => String(t.id) === String(templateId));
        if (!template) return;
        const config = template.config || {};
        const title = document.getElementById('reportTemplateTitle');
        const name = document.getElementById('reportTemplateName');
        if (title) title.value = config.title || 'GeoLog Well Report';
        if (name) name.value = template.name || '';
        const selected = new Set(config.sections || []);
        const mapping = {
            rbSectionRock: 'rock_source',
            rbSectionZonation: 'zonation',
            rbSectionProduction: 'production',
            rbSectionQc: 'qc',
            rbSectionCurves: 'curves',
        };
        for (const [id, key] of Object.entries(mapping)) {
            const el = document.getElementById(id);
            if (el) el.checked = selected.has(key);
        }
    },

    async saveReportTemplate() {
        const name = document.getElementById('reportTemplateName')?.value?.trim();
        if (!name) return GeoToast.warn('Template name is required.');
        const sections = this._reportSections();
        if (!sections.length) return GeoToast.warn('Select at least one section.');
        try {
            await this._api('/report-templates', {
                method: 'POST',
                body: JSON.stringify({
                    name,
                    title: document.getElementById('reportTemplateTitle')?.value || 'GeoLog Well Report',
                    sections,
                }),
            });
            GeoToast.success('Report template saved');
            const status = document.getElementById('reportTemplateStatus');
            if (status) status.textContent = `Saved ${name}`;
            await this.loadReportTemplates();
        } catch (e) {
            GeoToast.error('Template save failed: ' + e.message);
        }
    },

    async generateCustomReport() {
        if (!this.currentWell?.id) return GeoToast.warn('Load a well first.');
        const sections = this._reportSections();
        if (!sections.length) return GeoToast.warn('Select at least one section.');
        try {
            const blob = await this._apiBlob(`/wells/${this.currentWell.id}/report/custom.pdf`, {
                method: 'POST',
                body: JSON.stringify({
                    title: document.getElementById('reportTemplateTitle')?.value || 'GeoLog Well Report',
                    sections,
                }),
            });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${this.currentWell.name || 'well'}_custom_report.pdf`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            GeoToast.success('Custom report downloaded');
        } catch (e) {
            GeoToast.error('Custom report failed: ' + e.message);
        }
    },
});
