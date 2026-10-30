"""Prospect GRV and Monte Carlo STOIIP endpoints."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import Project

client = TestClient(app)
ADMIN = {"X-User-Role": "admin"}


def _project_id() -> int:
    db = SessionLocal()
    try:
        return int(db.query(Project.id).order_by(Project.id.asc()).first()[0])
    finally:
        db.close()


def _volume() -> bytes:
    textual = b" " * 3200
    binary = bytearray(400)
    ns = 12
    binary[16:18] = (2000).to_bytes(2, "big")
    binary[20:22] = (ns).to_bytes(2, "big")
    binary[24:26] = (5).to_bytes(2, "big")
    rng = np.random.default_rng(41)
    traces = []
    for inline in range(3):
        for crossline in range(3):
            header = bytearray(240)
            header[114:116] = (ns).to_bytes(2, "big")
            header[188:192] = (100 + inline).to_bytes(4, "big")
            header[192:196] = (200 + crossline).to_bytes(4, "big")
            data = rng.normal(0, 0.01, ns).astype(">f4")
            traces.append(bytes(header) + data.tobytes())
    return textual + bytes(binary) + b"".join(traces)


def _depth_surface(pid: int, with_spacing: bool = True) -> tuple[int, dict]:
    upload = client.post(
        f"/api/projects/{pid}/seismic",
        files={"file": ("prospect.sgy", _volume(), "application/octet-stream")},
        data={"name": "Prospect Volume"},
        headers=ADMIN,
    )
    assert upload.status_code == 201, upload.text
    line_id = upload.json()["id"]
    for index, inline in enumerate([100, 101, 102]):
        created = client.post(
            f"/api/seismic/{line_id}/horizons",
            json={
                "name": "Prospect Top",
                "mode": "inline",
                "section_value": inline,
                "picks": [
                    {"trace": 0, "sample": 2 + index},
                    {"trace": 1, "sample": 3 + index},
                    {"trace": 2, "sample": 4 + index},
                ],
            },
            headers=ADMIN,
        )
        assert created.status_code == 201, created.text
    body = {"name": "Prospect Surface", "horizon_name": "Prospect Top", "max_grid": 12}
    if with_spacing:
        body.update({"inline_spacing_m": 25, "crossline_spacing_m": 25})
    surface = client.post(
        f"/api/seismic/{line_id}/surfaces",
        json=body,
        headers=ADMIN,
    )
    assert surface.status_code == 201, surface.text
    surface_body = surface.json()
    if with_spacing:
        model = client.post(
            f"/api/projects/{pid}/velocity-models",
            json={"name": "Prospect 2000", "kind": "constant", "velocity_m_s": 2000},
            headers=ADMIN,
        )
        assert model.status_code == 201, model.text
        converted = client.post(
            f"/api/seismic/{line_id}/surfaces/{surface_body['id']}/depth",
            json={"velocity_model_id": model.json()["id"]},
            headers=ADMIN,
        )
        assert converted.status_code == 200, converted.text
        surface_body = converted.json()
    return line_id, surface_body


def _expected_grv(surface: dict, contact: float) -> float:
    grid = np.asarray(surface["depth_grid"], dtype=float)
    return float(np.sum(np.clip(contact - grid, 0, None)) * 25 * 25)


def test_prospect_monte_carlo_and_risking():
    pid = _project_id()
    line_id, surface = _depth_surface(pid)
    expected_grv = _expected_grv(surface, 1000.0)

    created = client.post(
        f"/api/projects/{pid}/prospects",
        json={
            "name": "Prospect A",
            "surface_id": surface["id"],
            "contact_depth_m": 1000,
            "porosity": 0.2,
            "water_saturation": 0.3,
            "recovery_factor": 0.4,
            "bo": 1.2,
            "iterations": 100,
            "seed": 7,
        },
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    result = body["result"]
    assert body["line_id"] == line_id
    assert body["grv_m3"] == round(expected_grv, 3)
    assert result["stoiip"]["p50_m3"] == round(expected_grv * 0.2 * 0.7 / 1.2, 3)
    assert result["recoverable"]["p50_m3"] == round(expected_grv * 0.2 * 0.7 / 1.2 * 0.4, 3)
    assert result["risked_stoiip"]["p50_m3"] == result["stoiip"]["p50_m3"]
    assert result["risk"]["probability"] == 1.0

    ranged = client.post(
        f"/api/projects/{pid}/prospects",
        json={
            "name": "Prospect range",
            "surface_id": surface["id"],
            "contact_depth_m": 1000,
            "porosity": {"low": 0.1, "mode": 0.2, "high": 0.3},
            "water_saturation": {"low": 0.2, "mode": 0.3, "high": 0.5},
            "recovery_factor": {"low": 0.2, "mode": 0.35, "high": 0.5},
            "risks": {"trap": 0.8, "reservoir": 0.7, "charge": 0.9, "seal": 0.6},
            "iterations": 500,
            "seed": 11,
        },
        headers=ADMIN,
    )
    assert ranged.status_code == 201, ranged.text
    ranged_result = ranged.json()["result"]
    assert ranged_result["stoiip"]["p90_m3"] <= ranged_result["stoiip"]["p50_m3"] <= ranged_result["stoiip"]["p10_m3"]
    assert ranged_result["risk"]["probability"] == round(0.8 * 0.7 * 0.9 * 0.6, 4)
    assert ranged_result["risked_stoiip"]["p50_m3"] < ranged_result["stoiip"]["p50_m3"]

    listed = client.get(f"/api/projects/{pid}/prospects", headers=ADMIN)
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} >= {body["id"], ranged.json()["id"]}
    assert "result" not in listed.json()[0]

    detail = client.get(f"/api/projects/{pid}/prospects/{body['id']}", headers=ADMIN)
    assert detail.status_code == 200
    assert detail.json()["result"]["iterations"] == 100

    deleted = client.delete(f"/api/projects/{pid}/prospects/{body['id']}", headers=ADMIN)
    assert deleted.status_code == 204


def test_prospect_requires_depth_and_spacing():
    pid = _project_id()
    _, time_surface = _depth_surface(pid, with_spacing=False)
    no_depth = client.post(
        f"/api/projects/{pid}/prospects",
        json={"name": "No depth", "surface_id": time_surface["id"], "contact_depth_m": 1000},
        headers=ADMIN,
    )
    assert no_depth.status_code == 400

    _, spaced_surface = _depth_surface(pid)
    above = client.post(
        f"/api/projects/{pid}/prospects",
        json={"name": "Above", "surface_id": spaced_surface["id"], "contact_depth_m": 1},
        headers=ADMIN,
    )
    assert above.status_code == 400


def test_gas_condensate_volumetrics():
    pid = _project_id()
    _, surface = _depth_surface(pid)
    expected_grv = _expected_grv(surface, 1000.0)
    giip = expected_grv * 0.2 * 0.7 / 0.005
    condensate = giip * 35.3147 / 1e6 * 30.0
    gas_boe = giip * 35.3147 / 5800.0

    created = client.post(
        f"/api/projects/{pid}/prospects",
        json={
            "name": "Gas prospect",
            "surface_id": surface["id"],
            "contact_depth_m": 1000,
            "fluid_type": "gas",
            "bg": 0.005,
            "condensate_yield": 30,
            "porosity": 0.2,
            "water_saturation": 0.3,
            "recovery_factor": 0.6,
            "iterations": 100,
            "seed": 3,
        },
        headers=ADMIN,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["fluid_type"] == "condensate"
    result = body["result"]
    assert result["fluid_type"] == "condensate"
    assert result["giip"]["p50_m3"] == round(giip, 3)
    assert result["condensate"]["p50_m3"] == round(condensate, 3)
    assert result["boe"]["p50_bbl"] == round(gas_boe + condensate, 3)
    assert result["recoverable_gas"]["p50_m3"] == round(giip * 0.6, 3)
    assert result["risked_giip"]["p50_m3"] == result["giip"]["p50_m3"]


def test_prospect_portfolio_emv_and_ranking():
    pid = _project_id()
    _, surface = _depth_surface(pid)
    prospects = []
    for name, porosity in (("Portfolio A", 0.16), ("Portfolio B", 0.24)):
        created = client.post(
            f"/api/projects/{pid}/prospects",
            json={
                "name": name,
                "surface_id": surface["id"],
                "contact_depth_m": 1000,
                "porosity": porosity,
                "water_saturation": 0.3,
                "recovery_factor": 0.4,
                "iterations": 100,
                "seed": 5,
            },
            headers=ADMIN,
        )
        assert created.status_code == 201, created.text
        prospects.append(created.json())

    expected = []
    for prospect in prospects:
        boe = prospect["result"]["recoverable_boe"]["p50_bbl"]
        expected.append((60 - 10) * boe - 1_000_000)

    portfolio = client.post(
        f"/api/projects/{pid}/prospect-portfolios",
        json={
            "name": "Portfolio 1",
            "prospect_ids": [item["id"] for item in prospects],
            "price_per_boe": 60,
            "opex_per_boe": 10,
            "capex": 1_000_000,
            "correlation": 1,
            "iterations": 200,
            "seed": 9,
        },
        headers=ADMIN,
    )
    assert portfolio.status_code == 201, portfolio.text
    body = portfolio.json()
    result = body["result"]
    assert result["portfolio"]["prospect_count"] == len(prospects)
    assert result["portfolio"]["total_emv"] == round(sum(expected), 3)
    assert result["portfolio"]["total_boe_p50"] == round(
        sum(item["result"]["recoverable_boe"]["p50_bbl"] for item in prospects), 3
    )
    ranks = [item["rank"] for item in result["prospects"]]
    assert ranks == sorted(ranks)
    assert result["prospects"][0]["emv"] >= result["prospects"][1]["emv"]

    listed = client.get(f"/api/projects/{pid}/prospect-portfolios", headers=ADMIN)
    assert listed.status_code == 200
    assert body["id"] in {item["id"] for item in listed.json()}

    detail = client.get(f"/api/projects/{pid}/prospect-portfolios/{body['id']}", headers=ADMIN)
    assert detail.status_code == 200
    assert detail.json()["result"]["portfolio"]["total_emv"] == result["portfolio"]["total_emv"]

    exported = client.get(
        f"/api/projects/{pid}/prospect-portfolios/{body['id']}/export.csv",
        headers=ADMIN,
    )
    assert exported.status_code == 200
    assert exported.text.splitlines()[0] == "rank,name,fluid_type,chance,boe_p90,boe_p50,boe_p10,net_revenue,emv"
    assert len(exported.text.splitlines()) == 1 + len(prospects)

    deleted = client.delete(f"/api/projects/{pid}/prospect-portfolios/{body['id']}", headers=ADMIN)
    assert deleted.status_code == 204

def test_grv_uses_base_surface_and_contact_whichever_is_shallower():
    from backend.volumetrics import grv_from_depth_grid

    top = [[2000.0, 2000.0], [2000.0, 2000.0]]
    base = [[2050.0, 2050.0], [2050.0, 2050.0]]
    common = {
        "inline_spacing_m": 25,
        "crossline_spacing_m": 25,
        "inlines": [100, 101],
        "crosslines": [200, 201],
    }
    below_base = grv_from_depth_grid(top, 2100, base_depth_grid=base, **common)
    assert below_base["grv_m3"] == 125000.0
    assert below_base["mean_reservoir_thickness_m"] == 50.0
    assert below_base["base_used"] is True

    above_base = grv_from_depth_grid(top, 2020, base_depth_grid=base, **common)
    assert above_base["grv_m3"] == 50000.0
    assert above_base["max_column_m"] == 20.0


def test_portfolio_capex_timing_and_correlated_risk():
    pid = _project_id()
    _, surface = _depth_surface(pid)
    prospects = []
    for name, porosity in (("Risk A", 0.18), ("Risk B", 0.26)):
        created = client.post(
            f"/api/projects/{pid}/prospects",
            json={
                "name": name,
                "surface_id": surface["id"],
                "contact_depth_m": 1000,
                "porosity": porosity,
                "water_saturation": 0.3,
                "recovery_factor": 0.4,
                "risk": 0.5,
                "iterations": 100,
                "seed": 2,
            },
            headers=ADMIN,
        )
        assert created.status_code == 201, created.text
        prospects.append(created.json())

    base = {
        "name": "Risk timing",
        "prospect_ids": [item["id"] for item in prospects],
        "price_per_boe": 60,
        "opex_per_boe": 10,
        "capex": 1_000_000,
        "dry_hole_cost": 0,
        "correlation": 1,
        "risk_correlation": 1,
        "iterations": 500,
        "seed": 12,
    }
    success = client.post(
        f"/api/projects/{pid}/prospect-portfolios",
        json={**base, "capex_timing": "success"},
        headers=ADMIN,
    )
    assert success.status_code == 201, success.text
    pre_drill = client.post(
        f"/api/projects/{pid}/prospect-portfolios",
        json={**base, "name": "Risk timing pre", "capex_timing": "pre_drill"},
        headers=ADMIN,
    )
    assert pre_drill.status_code == 201, pre_drill.text
    success_result = success.json()["result"]
    pre_result = pre_drill.json()["result"]
    assert success_result["portfolio"]["total_emv"] == pre_result["portfolio"]["total_emv"]
    assert pre_result["prospects"][0]["dry_net"] < success_result["prospects"][0]["dry_net"]
    assert pre_result["prospects"][0]["success_net"] > success_result["prospects"][0]["success_net"]

    risked = success_result["portfolio"]
    assert risked["risked_boe_p90"] == 0
    assert risked["risked_boe_p10"] > 0
    assert risked["risked_boe_mean"] < risked["mean_boe"]


def test_portfolio_full_correlation_matrix_and_validation():
    pid = _project_id()
    _, surface = _depth_surface(pid)
    prospects = []
    for name, porosity in (("Matrix A", 0.17), ("Matrix B", 0.25)):
        created = client.post(
            f"/api/projects/{pid}/prospects",
            json={
                "name": name,
                "surface_id": surface["id"],
                "contact_depth_m": 1000,
                "porosity": porosity,
                "water_saturation": 0.3,
                "recovery_factor": 0.4,
                "iterations": 100,
                "seed": 8,
            },
            headers=ADMIN,
        )
        assert created.status_code == 201, created.text
        prospects.append(created.json())

    matrix = [[1, 1], [1, 1]]
    response = client.post(
        f"/api/projects/{pid}/prospect-portfolios",
        json={
            "name": "Full matrix",
            "prospect_ids": [item["id"] for item in prospects],
            "price_per_boe": 60,
            "opex_per_boe": 10,
            "correlation_matrix": matrix,
            "risk_correlation_matrix": matrix,
            "iterations": 500,
            "seed": 4,
        },
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    summary = response.json()["result"]["portfolio"]
    expected_p90 = sum(item["result"]["recoverable_boe"]["p90_bbl"] for item in prospects)
    expected_p50 = sum(item["result"]["recoverable_boe"]["p50_bbl"] for item in prospects)
    expected_p10 = sum(item["result"]["recoverable_boe"]["p10_bbl"] for item in prospects)
    assert summary["total_boe_p90"] == pytest.approx(expected_p90, rel=1e-9)
    assert summary["total_boe_p50"] == pytest.approx(expected_p50, rel=1e-9)
    assert summary["total_boe_p10"] == pytest.approx(expected_p10, rel=1e-9)
    assert response.json()["result"]["inputs"]["correlation_matrix"] == matrix

    bad = client.post(
        f"/api/projects/{pid}/prospect-portfolios",
        json={
            "name": "Bad matrix",
            "prospect_ids": [item["id"] for item in prospects],
            "correlation_matrix": [[1, 2], [2, 1]],
        },
        headers=ADMIN,
    )
    assert bad.status_code == 400

    wrong_size = client.post(
        f"/api/projects/{pid}/prospect-portfolios",
        json={
            "name": "Wrong size",
            "prospect_ids": [item["id"] for item in prospects],
            "correlation_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        },
        headers=ADMIN,
    )
    assert wrong_size.status_code == 400
