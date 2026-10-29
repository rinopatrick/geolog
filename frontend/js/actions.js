/**
 * Delegated event actions.
 *
 * Inline event attributes are blocked by a strict CSP and mix markup with
 * behavior. Markup now carries data-action plus optional data-args; this file
 * resolves the dotted name at click/change/input time.
 */
(function () {
    function callAction(name, args, element, event) {
        const parts = String(name || '').split('.').filter(Boolean);
        if (!parts.length) return undefined;
        let owner = window;
        let fn = window;
        for (const part of parts) {
            owner = fn;
            fn = fn == null ? undefined : fn[part];
        }
        if (typeof fn !== 'function') {
            console.warn('GeoActions: unknown action', name);
            return undefined;
        }
        return fn.apply(owner, args);
    }

    function parseArgs(raw) {
        if (!raw) return [];
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [parsed];
        } catch (_) {
            console.warn('GeoActions: invalid data-args', raw);
            return [];
        }
    }

    function run(element, event) {
        const action = element.dataset.action;
        if (action) {
            const args = parseArgs(element.dataset.args);
            if (element.dataset.passEvent === 'true') args.push(event);
            if (element.dataset.argsValue === 'true') args.push(element.value);
            if (element.dataset.argsChecked === 'true') args.push(element.checked);
            callAction(action, args, element, event);
        }

        if (element.dataset.sortCurve) {
            window.app?._sortDataTable(element.dataset.sortCurve);
        }
        if (element.dataset.annId) {
            window.app?.deleteAnnotation(Number(element.dataset.annId));
        }
        if (element.dataset.templatePreview) {
            window._tmplPanel?._previewTemplate(element.dataset.templatePreview);
        }
        if (element.dataset.templateApply) {
            window._tmplPanel?._applyTemplate(element.dataset.templateApply);
        }
        if (element.dataset.clear) {
            const target = document.getElementById(element.dataset.clear);
            if (target) target.innerHTML = '';
        }
        if (element.dataset.templateIndex) {
            const index = Number(element.dataset.templateIndex);
            const template = window.app?.workflowTemplates?.[index];
            if (template) window.app.applyWorkflowTemplate(template.name);
        }

        if (element.dataset.toggleParent) {
            element.parentElement?.classList.toggle(element.dataset.toggleParent);
        }
        if (element.dataset.toggleSelf) {
            element.classList.toggle(element.dataset.toggleSelf);
        }
        if (element.dataset.toggleClass) {
            const [id, cls] = element.dataset.toggleClass.split(':');
            document.getElementById(id)?.classList.toggle(cls);
        }
        if (element.dataset.click) {
            document.getElementById(element.dataset.click)?.click();
        }
        if (element.dataset.hide) {
            const target = document.getElementById(element.dataset.hide);
            if (target) target.style.display = 'none';
        }
        if (element.dataset.toggleDisplay) {
            const [id, onValue, offValue] = element.dataset.toggleDisplay.split(':');
            const target = document.getElementById(id);
            if (target) target.style.display = target.style.display === 'none' ? onValue : offValue;
        }
        if (element.dataset.settext) {
            const target = document.getElementById(element.dataset.settext);
            if (target) target.textContent = element.value;
        }
        if (element.dataset.stopPropagation !== undefined) {
            event.stopPropagation();
        }
        if (element.dataset.hideSelfIfTarget !== undefined && event.target === element) {
            element.style.display = 'none';
        }
    }

    ['click', 'change', 'input'].forEach(type => {
        document.addEventListener(type, event => {
            const element = event.target.closest?.(
                '[data-action],[data-sort-curve],[data-ann-id],[data-template-index],[data-template-preview],[data-template-apply],[data-clear]'
            );
            if (!element) return;
            const handlerType = element.dataset.on || 'click';
            if (handlerType !== type) return;
            run(element, event);
        });
    });

    window.GeoActions = { run, callAction };
})();
