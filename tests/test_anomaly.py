"""A3: forecast-vs-actual anomaly detection (TDD Red).

Production-grade bar: seeded residuals, threshold flags, CUSUM trend
direction, no false positive on clean decline, guard rails on input.
"""

from __future__ import annotations

import pytest


def _clean_decline(n: int = 24, qi: float = 1000.0, d: float = 0.01):
    import numpy as np
    from datetime import date, timedelta

    dates = [date(2020, 1, 1) + timedelta(days=30 * i) for i in range(n)]
    rates = [qi * float(np.exp(-d * 30.0 * i)) for i in range(n)]
    return dates, rates


def test_clean_decline_has_no_flags():
    from backend.anomaly import detect_anomalies

    dates, rates = _clean_decline()
    out = detect_anomalies(dates, rates, threshold_pct=20.0, seed=7)
    assert out["anomaly_count"] == 0
    assert out["trend"] in ("declining", "stable")


def test_step_drop_is_flagged():
    from backend.anomaly import detect_anomalies

    dates, rates = _clean_decline()
    rates = list(rates)
    for i in range(18, 24):
        rates[i] *= 0.4
    out = detect_anomalies(dates, rates, threshold_pct=20.0, seed=7)
    assert out["anomaly_count"] >= 3
    flagged = [a["index"] for a in out["anomalies"] if a["kind"] == "drop"]
    assert min(flagged) >= 18


def test_upward_trend_detected():
    from backend.anomaly import detect_anomalies
    from datetime import date, timedelta

    dates = [date(2020, 1, 1) + timedelta(days=30 * i) for i in range(24)]
    rates = [500.0 + 10.0 * i for i in range(24)]
    out = detect_anomalies(dates, rates, threshold_pct=50.0, seed=7)
    assert out["trend"] == "growing"


def test_anomaly_rejects_bad_input():
    from backend.anomaly import detect_anomalies

    with pytest.raises(ValueError, match="at least"):
        detect_anomalies([], [], seed=1)
    with pytest.raises(ValueError, match="threshold"):
        detect_anomalies(*_clean_decline(), threshold_pct=0.0, seed=1)
    with pytest.raises(ValueError, match="length"):
        from datetime import date
        detect_anomalies([date(2020, 1, 1)], [1.0, 2.0], seed=1)

def test_anomaly_endpoint(make_well):
    from fastapi.testclient import TestClient
    from backend.main import SessionLocal, app
    from backend.models import ProductionData
    from datetime import date, timedelta
    import numpy as _np
    tclient = TestClient(app)
    admin = {"X-User-Role": "admin"}
    wid = make_well("ANOM-01", {"DEPT": [1000.0, 1001.0], "GR": [80.0, 82.0]})
    db = SessionLocal()
    try:
        for i in range(24):
            q = 1000.0 * float(_np.exp(-0.01 * 30.0 * i))
            if i >= 20:
                q *= 0.4
            db.add(ProductionData(well_id=wid, date=date(2020, 1, 1) + timedelta(days=30 * i), oil_rate=q))
        db.commit()
    finally:
        db.close()
    r = tclient.post(f"/api/wells/{wid}/production/anomalies", json={"threshold_pct": 20.0, "seed": 7}, headers=admin)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["anomaly_count"] >= 2
    assert data["trend"] == "declining"
    short = make_well("ANOM-SHORT", {"DEPT": [1000.0, 1001.0], "GR": [80.0, 82.0]})
    r2 = tclient.post(f"/api/wells/{short}/production/anomalies", json={}, headers=admin)
    assert r2.status_code == 400
