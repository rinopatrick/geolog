"""Saved report templates and custom PDF generation."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
INTERPRETER = {"X-User-Role": "interpreter"}
ADMIN = {"X-User-Role": "admin"}


def test_report_template_crud_and_custom_pdf(make_well):
    depth = np.arange(1000.0, 1010.0, 1.0)
    wid = make_well("CUSTOM-REPORT", {"DEPT": depth, "GR": np.full(len(depth), 50.0)})

    created = client.post(
        "/api/report-templates",
        json={
            "name": "Quick QC",
            "description": "QC + curves only",
            "sections": ["qc", "curves"],
            "title": "Quick QC Report",
        },
        headers=INTERPRETER,
    )
    assert created.status_code == 201, created.text
    template = created.json()
    template_id = template["id"]
    assert template["config"]["sections"] == ["qc", "curves"]

    listed = client.get("/api/report-templates", headers=INTERPRETER)
    assert listed.status_code == 200
    assert template_id in {item["id"] for item in listed.json()}

    updated = client.put(
        f"/api/report-templates/{template_id}",
        json={"name": "Quick QC v2", "sections": ["curves"], "title": "Curves"},
        headers=INTERPRETER,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["config"]["sections"] == ["curves"]

    report = client.post(
        f"/api/wells/{wid}/report/custom.pdf",
        json={"template_id": template_id},
        headers=INTERPRETER,
    )
    assert report.status_code == 200, report.text
    assert report.content[:4] == b"%PDF"
    assert report.headers["content-type"].startswith("application/pdf")

    inline = client.post(
        f"/api/wells/{wid}/report/custom.pdf",
        json={"title": "Inline", "sections": ["rock_source", "zonation", "production", "qc", "curves"]},
        headers=INTERPRETER,
    )
    assert inline.status_code == 200, inline.text
    assert inline.content[:4] == b"%PDF"

    deleted = client.delete(f"/api/report-templates/{template_id}", headers=ADMIN)
    assert deleted.status_code == 204


def test_custom_report_rejects_empty_sections(make_well):
    wid = make_well("CUSTOM-EMPTY", {"DEPT": np.array([1000.0]), "GR": np.array([1.0])})
    r = client.post(
        f"/api/wells/{wid}/report/custom.pdf",
        json={"sections": ["unknown"]},
        headers=INTERPRETER,
    )
    assert r.status_code == 400
