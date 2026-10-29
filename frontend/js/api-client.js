/**
 * HTTP client for GeoLogApp. Extracted from the app class so the request
 * lifecycle (single-flight, timeout, abort, error toasts) is testable on its own.
 */
const GeoAPI = {
    async _api(app, path, opts = {}) {
        const method = (opts.method || 'GET').toUpperCase();
        const dedupe = opts.dedupe !== false;
        const key = `${method}:${path}`;
        if (dedupe) {
            const pending = app._apiPendingRequests.get(key);
            if (pending) return pending;
        }
        const promise = GeoAPI._apiExecute(app, path, opts);
        if (dedupe) {
            app._apiPendingRequests.set(key, promise);
            promise.finally(() => {
                if (app._apiPendingRequests.get(key) === promise) {
                    app._apiPendingRequests.delete(key);
                }
            }).catch(() => {});
        }
        return promise;
    }
,

    async _apiExecute(app, path, opts = {}) {
        const timeoutMs = Number.isFinite(opts.timeoutMs) ? opts.timeoutMs : app.apiTimeoutMs;
        const externalSignal = opts.signal;
        const controller = new AbortController();
        let timeoutId = null;
        let externalAbortListener = null;

        if (externalSignal) {
            if (externalSignal.aborted) controller.abort();
            else {
                externalAbortListener = () => controller.abort();
                externalSignal.addEventListener('abort', externalAbortListener, { once: true });
            }
        }

        if (timeoutMs > 0) {
            timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        }

        try {
            const headers = opts.body instanceof FormData
                ? { ...app._authHeaders(), ...opts.headers }
                : { 'Content-Type': 'application/json', ...app._authHeaders(), ...opts.headers };
            const resp = await fetch('/api' + path, {
                headers,
                ...opts,
                signal: controller.signal,
            });
            if (!resp.ok) {
                let detail = `API error: ${resp.status}`;
                try {
                    const j = await resp.json();
                    detail = j?.detail || j?.message || j?.error || detail;
                } catch {}
                throw new Error(detail);
            }
            if (resp.status === 204) return null;
            return resp.json();
        } catch (e) {
            if (e.name === 'AbortError') {
                const msg = timeoutMs > 0 ? `Request timed out after ${Math.round(timeoutMs / 1000)}s` : 'Request was cancelled';
                GeoToast.error(msg);
                throw new Error(msg);
            }
            if (!navigator.onLine) {
                GeoToast.error('You appear to be offline. Check your network connection.');
            } else if (e.message !== 'Failed to fetch') {
                GeoToast.error(e.message || 'Network error');
            } else {
                GeoToast.error('Cannot reach server — is it running?');
            }
            throw e;
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
            if (externalSignal && externalAbortListener) {
                externalSignal.removeEventListener('abort', externalAbortListener);
            }
        }
    }
,

    async _apiBlob(app, path, opts = {}) {
        const { headers: optHeaders, ...rest } = opts;
        const headers = { ...app._authHeaders(), ...(optHeaders || {}) };
        if (typeof rest.body === 'string' && rest.body) headers['Content-Type'] = 'application/json';
        const resp = await fetch('/api' + path, {
            ...rest,
            headers,
        });
        if (!resp.ok) throw new Error(`Export error: ${resp.status}`);
        return resp.blob();
    }
,
};
window.GeoAPI = GeoAPI;
