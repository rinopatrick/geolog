"""Frontend delivery hygiene: no floating CDN script, CSP and API version."""

from __future__ import annotations

import re
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
    assert "script-src 'self';" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert r.headers["x-api-version"] == "v0"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"


def test_generated_html_escapes_server_values():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "frontend" / "js").glob("*.js"))
    )
    assert "escapeHtml(JSON.stringify(res, null, 2))" in sources
    assert "escapeHtml(String(e.message || e))" in sources
    assert "escapeHtml(nearest.wellName)" in sources
    assert "escapeHtml(result.wells.join(', '))" in sources


def test_markup_has_no_inline_event_handlers():
    js_files = sorted((ROOT / "frontend" / "js").glob("*.js"))
    for path in [ROOT / "frontend" / "index.html", *js_files]:
        text = path.read_text(encoding="utf-8")
        found = re.findall(
            r"\bon(?:click|change|input|submit|keyup|keydown|mouseover|mouseout|focus|blur)=",
            text,
        )
        assert not found, f"{path.name} still has inline handlers: {found[:5]}"

    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "/static/js/actions.js" in index
    assert "/static/js/sidebar.js" in index
    assert "/static/js/ui.js" in index
    assert "/static/js/api-client.js" in index
    assert "/static/js/bootstrap.js" in index
    assert "<script>" not in index
