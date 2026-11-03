"""Role and contract gates for report templates at the API seam.

Template deletion is admin-only. Building a custom PDF from an unknown
template id is a 404, not a silent fallback.
"""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
ADMIN = {"X-User-Role": "admin"}
VIEWER = {"X-User-Role": "viewer"}


def _make_template() -> int:
    r = client.post(
        "/api/report-templates",
        json={"name": "Gate check", "sections": ["qc"]},
        headers=INTERPRETER,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_template_delete_requires_admin():
    # Enforced by RBACWriteGuardMiddleware: every DELETE under /api/ needs
    # admin. The route-level require_admin is defense in depth.
    template_id = _make_template()
    denied = client.delete(f"/api/report-templates/{template_id}", headers=INTERPRETER)
    assert denied.status_code == 403
    denied_viewer = client.delete(f"/api/report-templates/{template_id}", headers=VIEWER)
    assert denied_viewer.status_code == 403
    ok = client.delete(f"/api/report-templates/{template_id}", headers=ADMIN)
    assert ok.status_code == 204


def test_custom_pdf_unknown_template_is_404(make_well):
    wid = make_well("TPL-404", {"DEPT": np.array([1000.0]), "GR": np.array([50.0])})
    r = client.post(
        f"/api/wells/{wid}/report/custom.pdf",
        json={"template_id": 999999},
        headers=INTERPRETER,
    )
    assert r.status_code == 404


def test_template_update_unknown_id_is_404():
    r = client.put(
        "/api/report-templates/999999",
        json={"name": "Ghost", "sections": ["qc"]},
        headers=INTERPRETER,
    )
    assert r.status_code == 404
