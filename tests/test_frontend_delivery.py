"""Frontend delivery hygiene: no floating CDN script, CSP and API version."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_lucide_is_vendored_and_pinned():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "unpkg.com/lucide@latest" not in index
    assert "/static/js/vendor/lucide.min.js" in index
    assert 'integrity="sha384-' in index
    vendor = ROOT / "frontend" / "js" / "vendor" / "lucide.min.js"
    assert vendor.is_file()
    assert vendor.stat().st_size > 100_000


def test_security_headers_include_csp_and_api_version():
    r = client.get("/api/health")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert r.headers["x-api-version"] == "v0"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"


def test_generated_html_escapes_server_values():
    app_js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    # The known sinks that embed arbitrary server/error text must escape it.
    assert "escapeHtml(JSON.stringify(res, null, 2))" in app_js
    assert "escapeHtml(String(e.message || e))" in app_js
    assert "escapeHtml(nearest.wellName)" in app_js
    assert "escapeHtml(result.wells.join(', '))" in app_js
