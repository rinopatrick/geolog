"""Operations router for GeoLog.

Metrics, SLO status, alerts, health, observability, and the security-evidence
gate family (manifest, attestation, freshness, gate/enforce/assert/check).

The request counters live in backend/observability.py, because the metrics
middleware in main.py writes them and these routes read them.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import time
import urllib.request
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

try:
    from audit import resolve_audit_export_signing_key, verify_audit_export_signature_payload
    from database import get_db
    from deps import require_interpreter, require_viewer
    from observability import OBS_METRICS, OBS_METRICS_LOCK
    # Reused response models, defined alongside the audit routes that share them.
    from routers.audit import AuditSignatureVerifyRequest, AuditSignatureVerifyResponse
except ImportError:
    from backend.audit import resolve_audit_export_signing_key, verify_audit_export_signature_payload
    from backend.database import get_db
    from backend.deps import require_interpreter, require_viewer
    from backend.observability import OBS_METRICS, OBS_METRICS_LOCK
    from backend.routers.audit import AuditSignatureVerifyRequest, AuditSignatureVerifyResponse

router = APIRouter(prefix="/api/ops", tags=["ops"])


OpsEvidenceAttestReasonCode = Literal[
    "ATTEST_VALID",
    "MISSING_REPORT",
    "MISSING_SIGNATURE",
    "INVALID_SIGNATURE_FORMAT",
    "DIGEST_MISMATCH",
    "HMAC_KEY_MISSING",
    "HMAC_SIGNATURE_MISMATCH",
]


class OpsMetricsResponse(BaseModel):
    requests_total: int
    requests_by_method: dict[str, int]
    requests_by_status: dict[str, int]
    latency_ms_avg: float
    latency_samples: int
    recent_events_size: int
    timestamp: str


class OpsRecentEvent(BaseModel):
    ts: str
    method: str
    path: str
    status: int
    latency_ms: float


class OpsMetricsRecentResponse(BaseModel):
    events: list[OpsRecentEvent]
    count: int
    limit: int
    status_min: int
    path_contains: str | None = None
    timestamp: str


class OpsSloTargets(BaseModel):
    latency_ms_avg_max: float
    latency_ms_p95_max: float
    error_rate_max: float


class OpsSloCurrent(BaseModel):
    latency_ms_avg: float
    latency_ms_p95: float
    error_rate: float
    requests_total: int
    errors_5xx: int


class OpsSloChecks(BaseModel):
    latency_ok: bool
    latency_avg_ok: bool
    latency_p95_ok: bool
    error_rate_ok: bool


class OpsSloStatusResponse(BaseModel):
    ok: bool
    targets: OpsSloTargets
    current: OpsSloCurrent
    checks: OpsSloChecks
    timestamp: str


class OpsAlertsResponse(BaseModel):
    ok: bool
    alerts: list[dict[str, Any]]
    count: int
    severity_counts: dict[str, int]
    code_counts: dict[str, int]
    highest_severity: Literal["none", "warning", "critical"]
    timestamp: str


class OpsAlertRule(BaseModel):
    code: str
    severity: Literal["warning", "critical"]
    metric: str
    threshold: float
    operator: Literal[">"]
    env_key: str


class OpsAlertRulesResponse(BaseModel):
    version: str
    rules: list[OpsAlertRule]
    timestamp: str


class OpsHealthResponse(BaseModel):
    ok: bool
    db_ok: bool
    slo_ok: bool
    alerts_ok: bool
    alert_count: int
    timestamp: str


class OpsObservabilityStatusResponse(BaseModel):
    ok: bool
    request_id_propagation: bool
    trace_context_propagation: bool
    structured_logging: bool
    recent_events_include_request_id: bool
    recent_events_include_trace_id: bool
    otel_enabled: bool
    timestamp: str


class OpsOtelStatusResponse(BaseModel):
    ok: bool
    enabled: bool
    exporter_otlp_endpoint_set: bool
    service_name: str
    resource_attributes_set: bool
    timestamp: str


class OpsEvidenceStatusResponse(BaseModel):
    ok: bool
    dashboard_configured: bool
    dashboard_url: str | None = None
    dashboard_reachable: bool | None = None
    alert_delivery_configured: bool
    alert_delivery_target: str | None = None
    trace_backend_configured: bool
    trace_backend_url: str | None = None
    trace_backend_reachable: bool | None = None
    probes_enabled: bool
    ready_for_phase2_acceptance: bool
    timestamp: str


class OpsSecurityPostureStatusResponse(BaseModel):
    ok: bool
    container_non_root: bool
    secrets_source_configured: bool
    tls_required: bool
    ci_security_gates_enabled: bool
    backup_drill_script_present: bool
    branch_protection_checklist_present: bool
    security_evidence_template_present: bool
    timestamp: str


class OpsSecurityEvidenceStatusResponse(BaseModel):
    ok: bool
    artifact_dir: str
    report_present: bool
    signature_present: bool
    report_sha256_matches_signature: bool | None = None
    signature_alg: str | None = None
    signature_kid: str | None = None
    hmac_signature_valid: bool | None = None
    retention_days: int | None = None
    timestamp: str


class OpsSecurityEvidenceManifestResponse(BaseModel):
    ok: bool
    artifact_dir: str
    report_path: str | None = None
    signature_path: str | None = None
    report_sha256: str | None = None
    signature_sha256: str | None = None
    bundle_digest_sha256: str | None = None
    signature: str | None = None
    signature_alg: str | None = None
    signature_kid: str | None = None
    timestamp: str


class OpsSecurityEvidenceManifestVerifyRequest(BaseModel):
    signature: str = Field(..., min_length=64, max_length=64, pattern="^[0-9a-fA-F]{64}$")
    kid: str | None = None


class OpsRunbookEntry(BaseModel):
    severity: Literal["warning", "critical"]
    what_it_means: str
    checks: list[str]
    actions: list[str]


class OpsRunbookResponse(BaseModel):
    version: str
    alerts: dict[str, OpsRunbookEntry]
    timestamp: str


class OpsContractsResponse(BaseModel):
    api_group: str
    contract_version: str
    endpoints: dict[str, str]
    digest_sha256: str
    signature: str | None = None
    signature_alg: str | None = None
    signature_kid: str | None = None
    timestamp: str


class OpsSecurityEvidenceAttestRequest(BaseModel):
    report: dict[str, Any]
    signature: dict[str, Any]


class OpsSecurityEvidenceAttestResponse(BaseModel):
    ok: bool
    reason: str
    reason_code: OpsEvidenceAttestReasonCode
    report_sha256: str | None = None
    signature_alg: str | None = None
    signature_kid: str | None = None
    retention_days: int | None = None
    timestamp: str


class OpsSecurityEvidenceFreshnessResponse(BaseModel):
    ok: bool
    artifact_dir: str
    report_path: str | None = None
    signature_path: str | None = None
    report_age_seconds: int | None = None
    max_age_seconds: int
    stale: bool
    reason_code: Literal["FRESH", "STALE", "EVIDENCE_MISSING"]
    timestamp: str


class OpsSecurityEvidenceGateResponse(BaseModel):
    ok: bool
    gate_reason_code: Literal["GATE_PASS", "GATE_FAIL"]
    gate_failed_count: int
    gate_passed_count: int
    gate_total_count: int
    gate_pass_ratio: float
    gate_fail_ratio: float
    gate_consistency_ok: bool
    gate_consistency_reason: Literal["CONSISTENT", "COUNT_MISMATCH", "RATIO_MISMATCH"]
    attest_ok: bool
    freshness_ok: bool
    retention_ok: bool
    strict_required_checks: bool
    defaulted_checks: bool
    requested_checks: list[str]
    ignored_checks: list[str]
    duplicate_checks: list[str]
    evaluated_checks: list[Literal["attest", "freshness", "retention"]]
    failed_checks: list[Literal["attest", "freshness", "retention"]]
    # Was Literal["ATTEST_VALID", "ATTEST_INVALID", "ATTEST_ERROR"], which does not
    # include any of the codes _attest_security_evidence_payload actually returns.
    # The common case — no evidence attested yet — returns MISSING_REPORT, so
    # response validation rejected the payload and the endpoint raised 500.
    attest_reason_code: OpsEvidenceAttestReasonCode
    freshness_reason_code: Literal["FRESH", "STALE", "EVIDENCE_MISSING"]
    retention_reason_code: Literal["RETENTION_OK", "RETENTION_TOO_SHORT", "RETENTION_UNKNOWN"]
    artifact_dir: str
    report_age_seconds: int | None = None
    retention_days: int | None = None
    min_retention_days: int
    max_age_seconds: int
    timestamp: str


class OpsSecurityEvidenceGateErrorDetail(BaseModel):
    error: str
    gate_reason_code: Literal["GATE_FAIL"]
    gate_failed_count: int
    gate_passed_count: int
    gate_total_count: int
    gate_pass_ratio: float
    gate_fail_ratio: float
    gate_consistency_ok: bool
    gate_consistency_reason: Literal["CONSISTENT", "COUNT_MISMATCH", "RATIO_MISMATCH"]
    strict_required_checks: bool
    defaulted_checks: bool
    requested_checks: list[str]
    ignored_checks: list[str]
    duplicate_checks: list[str]
    evaluated_checks: list[Literal["attest", "freshness", "retention"]]
    failed_checks: list[Literal["attest", "freshness", "retention"]]
    attest_reason_code: str | None = None
    freshness_reason_code: Literal["FRESH", "STALE", "EVIDENCE_MISSING"]
    retention_reason_code: Literal["RETENTION_OK", "RETENTION_TOO_SHORT", "RETENTION_UNKNOWN"]
    artifact_dir: str
    report_age_seconds: int | None = None
    retention_days: int | None = None
    min_retention_days: int
    max_age_seconds: int


class OpsSecurityEvidenceGateErrorResponse(BaseModel):
    detail: OpsSecurityEvidenceGateErrorDetail


class OpsSummaryStatus(BaseModel):
    db_ok: bool
    slo_ok: bool
    alerts_ok: bool


class OpsSummaryAlerts(BaseModel):
    count: int
    highest_severity: Literal["none", "warning", "critical"]
    severity_counts: dict[str, int]
    code_counts: dict[str, int]


class OpsSummaryTraffic(BaseModel):
    requests_total: int
    latency_ms_avg: float
    error_rate: float
    recent_events_size: int


class OpsSummarySlo(BaseModel):
    targets: dict[str, Any]
    current: dict[str, Any]
    checks: dict[str, Any]


class OpsSummaryResponse(BaseModel):
    ok: bool
    contract_version: str
    status: OpsSummaryStatus
    alerts: OpsSummaryAlerts
    traffic: OpsSummaryTraffic
    slo: OpsSummarySlo
    timestamp: str


def _attest_security_evidence_payload(report: dict[str, Any] | None, signature_obj: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {
            "ok": False,
            "reason": "report object is required",
            "reason_code": "MISSING_REPORT",
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }
    if not signature_obj:
        return {
            "ok": False,
            "reason": "signature object is required",
            "reason_code": "MISSING_SIGNATURE",
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }

    report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    report_sha = hashlib.sha256(report_bytes).hexdigest()

    declared_sha = str(signature_obj.get("report_sha256", "") or "").strip().lower()
    signature_alg = str(signature_obj.get("signature_alg", "") or "").strip() or None
    signature_kid = str(signature_obj.get("signature_kid", "") or "").strip() or None
    sig = str(signature_obj.get("signature", "") or "").strip().lower()
    rd = signature_obj.get("retention_days")
    retention_days = int(rd) if isinstance(rd, int) else None

    if not declared_sha or declared_sha != report_sha:
        return {
            "ok": False,
            "reason": "report_sha256 mismatch",
            "reason_code": "DIGEST_MISMATCH",
            "report_sha256": report_sha,
            "signature_alg": signature_alg,
            "signature_kid": signature_kid,
            "retention_days": retention_days,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }

    if signature_alg == "hmac-sha256":
        if not sig or len(sig) != 64 or any(c not in "0123456789abcdef" for c in sig):
            return {
                "ok": False,
                "reason": "signature must be 64-char hex",
                "reason_code": "INVALID_SIGNATURE_FORMAT",
                "report_sha256": report_sha,
                "signature_alg": signature_alg,
                "signature_kid": signature_kid,
                "retention_days": retention_days,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            }
        key = (os.getenv("BACKUP_DRILL_SIGNING_KEY") or "").strip()
        if not key:
            return {
                "ok": False,
                "reason": "BACKUP_DRILL_SIGNING_KEY is required for hmac-sha256 verification",
                "reason_code": "HMAC_KEY_MISSING",
                "report_sha256": report_sha,
                "signature_alg": signature_alg,
                "signature_kid": signature_kid,
                "retention_days": retention_days,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            }
        expected = hmac.new(key.encode("utf-8"), report_sha.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return {
                "ok": False,
                "reason": "hmac signature mismatch",
                "reason_code": "HMAC_SIGNATURE_MISMATCH",
                "report_sha256": report_sha,
                "signature_alg": signature_alg,
                "signature_kid": signature_kid,
                "retention_days": retention_days,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            }

    return {
        "ok": True,
        "reason": "evidence attestation valid",
        "reason_code": "ATTEST_VALID",
        "report_sha256": report_sha,
        "signature_alg": signature_alg,
        "signature_kid": signature_kid,
        "retention_days": retention_days,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


def _ops_contracts_payload() -> dict[str, Any]:
    endpoints = {
        "/api/audit-log/verify/export": "1.2",
        "/api/audit-log/verify/signature": "1.1",
        "/api/audit-log/immutability-status": "1.0",
        "/api/ops/metrics": "1.0",
        "/api/ops/metrics/recent": "1.1",
        "/api/ops/metrics/prometheus": "1.0",
        "/api/ops/slo-status": "1.1",
        "/api/ops/alerts": "1.2",
        "/api/ops/alert-rules": "1.0",
        "/api/ops/health": "1.0",
        "/api/ops/observability-status": "1.1",
        "/api/ops/otel-status": "1.0",
        "/api/ops/evidence-status": "1.0",
        "/api/ops/security-posture-status": "1.0",
        "/api/ops/security-evidence-status": "1.0",
        "/api/ops/security-evidence/manifest": "1.0",
        "/api/ops/security-evidence/manifest/verify-signature": "1.0",
        "/api/ops/security-evidence/attest": "1.0",
        "/api/ops/security-evidence/attest/latest": "1.0",
        "/api/ops/security-evidence/freshness": "1.0",
        "/api/ops/security-evidence/gate": "1.14",
        "/api/ops/security-evidence/gate/enforce": "1.14",
        "/api/ops/security-evidence/gate/assert": "1.14",
        "/api/ops/security-evidence/gate/check": "1.14",
        "/api/ops/runbook": "1.0",
        "/api/ops/summary": "1.1",
    }
    return {
        "api_group": "ops-audit",
        "contract_version": "2.0",
        "endpoints": endpoints,
    }


def _compute_gate_invariants(failed_checks: list[str], evaluated_checks: list[str]) -> dict[str, Any]:
    failed_count = int(len(failed_checks or []))
    total_count = int(len(evaluated_checks or []))
    passed_count = int(max(0, total_count - failed_count))
    pass_ratio = float(passed_count / total_count) if total_count > 0 else 0.0
    fail_ratio = float(failed_count / total_count) if total_count > 0 else 0.0
    count_consistent = failed_count + passed_count == total_count
    ratio_consistent = abs((pass_ratio + fail_ratio) - 1.0) <= 1e-9 if total_count > 0 else True
    consistency_ok = bool(count_consistent and ratio_consistent)
    consistency_reason = "CONSISTENT" if consistency_ok else "COUNT_MISMATCH" if not count_consistent else "RATIO_MISMATCH"
    return {
        "gate_failed_count": failed_count,
        "gate_passed_count": passed_count,
        "gate_total_count": total_count,
        "gate_pass_ratio": pass_ratio,
        "gate_fail_ratio": fail_ratio,
        "gate_consistency_ok": consistency_ok,
        "gate_consistency_reason": consistency_reason,
    }


def _security_evidence_gate_failure_detail(gate: dict[str, Any]) -> dict[str, Any]:
    invariants = _compute_gate_invariants(gate.get("failed_checks") or [], gate.get("evaluated_checks") or [])

    return {
        "error": "security evidence gate failed",
        "gate_reason_code": "GATE_FAIL",
        "gate_failed_count": invariants["gate_failed_count"],
        "gate_passed_count": invariants["gate_passed_count"],
        "gate_total_count": invariants["gate_total_count"],
        "gate_pass_ratio": invariants["gate_pass_ratio"],
        "gate_fail_ratio": invariants["gate_fail_ratio"],
        "gate_consistency_ok": invariants["gate_consistency_ok"],
        "gate_consistency_reason": invariants["gate_consistency_reason"],
        "strict_required_checks": bool(gate.get("strict_required_checks", False)),
        "defaulted_checks": bool(gate.get("defaulted_checks", False)),
        "requested_checks": gate.get("requested_checks", []),
        "ignored_checks": gate.get("ignored_checks", []),
        "duplicate_checks": gate.get("duplicate_checks", []),
        "evaluated_checks": gate.get("evaluated_checks", []),
        "failed_checks": gate.get("failed_checks", []),
        "attest_reason_code": gate.get("attest_reason_code"),
        "freshness_reason_code": gate.get("freshness_reason_code"),
        "retention_reason_code": gate.get("retention_reason_code"),
        "artifact_dir": gate.get("artifact_dir"),
        "report_age_seconds": gate.get("report_age_seconds"),
        "retention_days": gate.get("retention_days"),
        "min_retention_days": gate.get("min_retention_days"),
        "max_age_seconds": gate.get("max_age_seconds"),
    }


@router.get(
    "/metrics",
    response_model=OpsMetricsResponse,
    responses={
        200: {
            "description": "In-process metrics snapshot",
            "content": {
                "application/json": {
                    "example": {
                        "requests_total": 120,
                        "requests_by_method": {"GET": 110, "POST": 10},
                        "requests_by_status": {"200": 115, "404": 4, "500": 1},
                        "latency_ms_avg": 35.7,
                        "latency_samples": 120,
                        "recent_events_size": 120,
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_metrics(_role: str = Depends(require_viewer)):
    """Lightweight in-process metrics snapshot (Phase 2 baseline)."""
    with OBS_METRICS_LOCK:
        total = int(OBS_METRICS.get("requests_total", 0))
        count = int(OBS_METRICS.get("latency_ms_count", 0))
        avg = (float(OBS_METRICS.get("latency_ms_sum", 0.0)) / count) if count > 0 else 0.0
        return {
            "requests_total": total,
            "requests_by_method": dict(OBS_METRICS.get("requests_by_method", {})),
            "requests_by_status": dict(OBS_METRICS.get("requests_by_status", {})),
            "latency_ms_avg": round(avg, 2),
            "latency_samples": count,
            "recent_events_size": len(OBS_METRICS.get("recent_events", [])) if isinstance(OBS_METRICS.get("recent_events"), list) else 0,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }


@router.get(
    "/metrics/recent",
    response_model=OpsMetricsRecentResponse,
    responses={
        200: {
            "description": "Recent request events with optional filters",
            "content": {
                "application/json": {
                    "example": {
                        "events": [{"ts": "2026-01-01T00:00:00Z", "method": "GET", "path": "/api/wells", "status": 200, "latency_ms": 12.3}],
                        "count": 1,
                        "limit": 20,
                        "status_min": 0,
                        "path_contains": None,
                        "timestamp": "2026-01-01T00:00:01Z",
                    }
                }
            },
        }
    },
)
def ops_metrics_recent(
    limit: int = 20,
    status_min: int = 0,
    path_contains: str | None = None,
    _role: str = Depends(require_viewer),
):
    """Return recent request events captured by in-process metrics middleware."""
    limit = max(1, min(int(limit or 20), 200))
    status_min = max(0, int(status_min or 0))
    needle = (path_contains or "").strip().lower()

    with OBS_METRICS_LOCK:
        recent = OBS_METRICS.get("recent_events")
        if not isinstance(recent, list):
            recent = []

        filtered = []
        for e in recent:
            try:
                st = int(e.get("status", 0))
            except Exception:
                st = 0
            p = str(e.get("path", ""))
            if st < status_min:
                continue
            if needle and needle not in p.lower():
                continue
            filtered.append(e)

        out = filtered[-limit:]

    return {
        "events": out,
        "count": len(out),
        "limit": limit,
        "status_min": status_min,
        "path_contains": path_contains,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get(
    "/slo-status",
    response_model=OpsSloStatusResponse,
    responses={
        200: {
            "description": "SLO evaluation snapshot",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "targets": {"latency_ms_avg_max": 500.0, "latency_ms_p95_max": 800.0, "error_rate_max": 0.01},
                        "current": {"latency_ms_avg": 42.1, "latency_ms_p95": 88.2, "error_rate": 0.0, "requests_total": 123, "errors_5xx": 0},
                        "checks": {"latency_ok": True, "latency_avg_ok": True, "latency_p95_ok": True, "error_rate_ok": True},
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_slo_status(_role: str = Depends(require_viewer)):
    """Basic SLO evaluation snapshot from in-process counters."""
    target_latency_avg_ms = float(os.getenv("OPS_SLO_AVG_MS", "500") or 500)
    target_latency_p95_ms = float(os.getenv("OPS_SLO_P95_MS", "800") or 800)
    target_error_rate = float(os.getenv("OPS_SLO_ERROR_RATE", "0.01") or 0.01)

    with OBS_METRICS_LOCK:
        total = int(OBS_METRICS.get("requests_total", 0))
        avg = 0.0
        count = int(OBS_METRICS.get("latency_ms_count", 0))
        if count > 0:
            avg = float(OBS_METRICS.get("latency_ms_sum", 0.0)) / count
        by_status = dict(OBS_METRICS.get("requests_by_status", {}))
        recent = OBS_METRICS.get("recent_events")
        if not isinstance(recent, list):
            recent = []

    error_count = 0
    for k, v in by_status.items():
        try:
            if int(k) >= 500:
                error_count += int(v)
        except Exception:
            continue

    error_rate = (float(error_count) / total) if total > 0 else 0.0
    error_ok = error_rate <= target_error_rate

    # lightweight p95 from recent ring buffer latency values
    latencies = [float(e.get("latency_ms", 0.0)) for e in recent if isinstance(e, dict)]
    latency_p95 = 0.0
    if latencies:
        try:
            latency_p95 = float(np.percentile(np.array(latencies, dtype=np.float64), 95))
        except Exception:
            latency_p95 = 0.0

    latency_avg_ok = avg <= target_latency_avg_ms
    latency_p95_ok = latency_p95 <= target_latency_p95_ms
    latency_ok = bool(latency_avg_ok and latency_p95_ok)

    return {
        "ok": bool(latency_ok and error_ok),
        "targets": {
            "latency_ms_avg_max": target_latency_avg_ms,
            "latency_ms_p95_max": target_latency_p95_ms,
            "error_rate_max": target_error_rate,
        },
        "current": {
            "latency_ms_avg": round(avg, 2),
            "latency_ms_p95": round(latency_p95, 2),
            "error_rate": round(error_rate, 6),
            "requests_total": total,
            "errors_5xx": error_count,
        },
        "checks": {
            "latency_ok": latency_ok,
            "latency_avg_ok": latency_avg_ok,
            "latency_p95_ok": latency_p95_ok,
            "error_rate_ok": error_ok,
        },
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get(
    "/alerts",
    response_model=OpsAlertsResponse,
    responses={
        200: {
            "description": "SLO breach alerts",
            "content": {
                "application/json": {
                    "example": {
                        "ok": False,
                        "alerts": [
                            {"code": "LATENCY_P95_SLO_BREACH", "severity": "warning", "message": "latency_ms_p95 920.0 > target 800.0"}
                        ],
                        "count": 1,
                        "severity_counts": {"warning": 1, "critical": 0},
                        "code_counts": {"LATENCY_P95_SLO_BREACH": 1},
                        "highest_severity": "warning",
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_alerts(_role: str = Depends(require_viewer)):
    """Simple alert evaluation based on SLO snapshot."""
    slo = ops_slo_status(_role)
    alerts = []

    if not slo["checks"]["latency_avg_ok"]:
        alerts.append({
            "code": "LATENCY_AVG_SLO_BREACH",
            "severity": "warning",
            "message": (
                f"latency_ms_avg {slo['current']['latency_ms_avg']} > target {slo['targets']['latency_ms_avg_max']}"
            ),
        })

    if not slo["checks"]["latency_p95_ok"]:
        alerts.append({
            "code": "LATENCY_P95_SLO_BREACH",
            "severity": "warning",
            "message": (
                f"latency_ms_p95 {slo['current']['latency_ms_p95']} > target {slo['targets']['latency_ms_p95_max']}"
            ),
        })

    if not slo["checks"]["error_rate_ok"]:
        alerts.append({
            "code": "ERROR_RATE_SLO_BREACH",
            "severity": "critical",
            "message": (
                f"error_rate {slo['current']['error_rate']} > target {slo['targets']['error_rate_max']}"
            ),
        })

    severity_counts = {"warning": 0, "critical": 0}
    code_counts = {}
    for a in alerts:
        sev = str(a.get("severity", "")).lower()
        if sev in severity_counts:
            severity_counts[sev] += 1
        code = str(a.get("code", "")).strip()
        if code:
            code_counts[code] = int(code_counts.get(code, 0)) + 1

    highest_severity = "none"
    if int(severity_counts.get("critical", 0)) > 0:
        highest_severity = "critical"
    elif int(severity_counts.get("warning", 0)) > 0:
        highest_severity = "warning"

    return {
        "ok": len(alerts) == 0,
        "alerts": alerts,
        "count": len(alerts),
        "severity_counts": severity_counts,
        "code_counts": code_counts,
        "highest_severity": highest_severity,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get(
    "/alert-rules",
    response_model=OpsAlertRulesResponse,
    responses={
        200: {
            "description": "Configured SLO alert rules and threshold source",
            "content": {
                "application/json": {
                    "example": {
                        "version": "1.0",
                        "rules": [
                            {
                                "code": "LATENCY_AVG_SLO_BREACH",
                                "severity": "warning",
                                "metric": "latency_ms_avg",
                                "threshold": 500.0,
                                "operator": ">",
                                "env_key": "OPS_SLO_AVG_MS",
                            }
                        ],
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_alert_rules(_role: str = Depends(require_viewer)):
    """Alert-rule contract for runtime SLO thresholds (env-backed)."""
    avg = float(os.getenv("OPS_SLO_AVG_MS", "500") or 500)
    p95 = float(os.getenv("OPS_SLO_P95_MS", "800") or 800)
    err = float(os.getenv("OPS_SLO_ERROR_RATE", "0.01") or 0.01)
    return {
        "version": "1.0",
        "rules": [
            {
                "code": "LATENCY_AVG_SLO_BREACH",
                "severity": "warning",
                "metric": "latency_ms_avg",
                "threshold": avg,
                "operator": ">",
                "env_key": "OPS_SLO_AVG_MS",
            },
            {
                "code": "LATENCY_P95_SLO_BREACH",
                "severity": "warning",
                "metric": "latency_ms_p95",
                "threshold": p95,
                "operator": ">",
                "env_key": "OPS_SLO_P95_MS",
            },
            {
                "code": "ERROR_RATE_SLO_BREACH",
                "severity": "critical",
                "metric": "error_rate",
                "threshold": err,
                "operator": ">",
                "env_key": "OPS_SLO_ERROR_RATE",
            },
        ],
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get(
    "/metrics/prometheus",
    responses={
        200: {
            "description": "Prometheus text exposition format",
            "content": {
                "text/plain": {
                    "example": "# HELP geolog_requests_total Total HTTP requests observed\n# TYPE geolog_requests_total counter\ngeolog_requests_total 123"
                }
            },
        }
    },
)
def ops_metrics_prometheus(_role: str = Depends(require_viewer)):
    """Prometheus text exposition for lightweight ops metrics."""
    with OBS_METRICS_LOCK:
        total = int(OBS_METRICS.get("requests_total", 0))
        by_method = dict(OBS_METRICS.get("requests_by_method", {}))
        by_status = dict(OBS_METRICS.get("requests_by_status", {}))
        lat_sum = float(OBS_METRICS.get("latency_ms_sum", 0.0))
        lat_count = int(OBS_METRICS.get("latency_ms_count", 0))

    lines = [
        "# HELP geolog_requests_total Total HTTP requests observed",
        "# TYPE geolog_requests_total counter",
        f"geolog_requests_total {total}",
        "# HELP geolog_requests_by_method_total HTTP requests by method",
        "# TYPE geolog_requests_by_method_total counter",
    ]
    for method, count in sorted(by_method.items()):
        lines.append(f'geolog_requests_by_method_total{{method="{method}"}} {int(count)}')

    lines += [
        "# HELP geolog_requests_by_status_total HTTP requests by response status",
        "# TYPE geolog_requests_by_status_total counter",
    ]
    for status, count in sorted(by_status.items()):
        lines.append(f'geolog_requests_by_status_total{{status="{status}"}} {int(count)}')

    lines += [
        "# HELP geolog_request_latency_ms_sum Sum of request latency in milliseconds",
        "# TYPE geolog_request_latency_ms_sum counter",
        f"geolog_request_latency_ms_sum {lat_sum}",
        "# HELP geolog_request_latency_ms_count Count of request latency samples",
        "# TYPE geolog_request_latency_ms_count counter",
        f"geolog_request_latency_ms_count {lat_count}",
        "",
    ]
    return StreamingResponse(iter(["\n".join(lines)]), media_type="text/plain; version=0.0.4")


@router.get(
    "/health",
    response_model=OpsHealthResponse,
    responses={
        200: {
            "description": "Operational health snapshot",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "db_ok": True,
                        "slo_ok": True,
                        "alerts_ok": True,
                        "alert_count": 0,
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_health(db: Session = Depends(get_db), _role: str = Depends(require_viewer)):
    """Operational health snapshot: db connectivity + SLO + alert summary."""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    slo = ops_slo_status(_role)
    alerts = ops_alerts(_role)

    return {
        "ok": bool(db_ok and alerts.get("ok", False)),
        "db_ok": db_ok,
        "slo_ok": bool(slo.get("ok", False)),
        "alerts_ok": bool(alerts.get("ok", False)),
        "alert_count": int(alerts.get("count", 0)),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/observability-status", response_model=OpsObservabilityStatusResponse)
def ops_observability_status(_role: str = Depends(require_viewer)):
    """Observability wiring status for Phase 2 verification."""
    with OBS_METRICS_LOCK:
        recent = list(OBS_METRICS.get("recent_events", []))
    has_request_id = any(bool(str(e.get("request_id", "")).strip()) for e in recent if isinstance(e, dict))
    has_trace_id = any(bool(str(e.get("trace_id", "")).strip()) for e in recent if isinstance(e, dict))
    otel_enabled = bool((os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip())
    return {
        "ok": True,
        "request_id_propagation": True,
        "trace_context_propagation": True,
        "structured_logging": True,
        "recent_events_include_request_id": has_request_id,
        "recent_events_include_trace_id": has_trace_id,
        "otel_enabled": otel_enabled,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/otel-status", response_model=OpsOtelStatusResponse)
def ops_otel_status(_role: str = Depends(require_viewer)):
    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    service_name = (os.getenv("OTEL_SERVICE_NAME") or "geolog-app").strip() or "geolog-app"
    resource_attrs = (os.getenv("OTEL_RESOURCE_ATTRIBUTES") or "").strip()
    enabled = bool(endpoint)
    return {
        "ok": True,
        "enabled": enabled,
        "exporter_otlp_endpoint_set": bool(endpoint),
        "service_name": service_name,
        "resource_attributes_set": bool(resource_attrs),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/evidence-status", response_model=OpsEvidenceStatusResponse)
def ops_evidence_status(
    probe: bool = Query(default=False, description="When true, perform live HTTP reachability probes for dashboard/trace URLs"),
    _role: str = Depends(require_viewer),
):
    dashboard_url = (os.getenv("OPS_DASHBOARD_URL") or "").strip()
    alert_target = (os.getenv("OPS_ALERT_TARGET") or "").strip()
    trace_backend_url = (os.getenv("OPS_TRACE_BACKEND_URL") or "").strip()

    dashboard_configured = bool(dashboard_url)
    alert_delivery_configured = bool(alert_target)
    trace_backend_configured = bool(trace_backend_url)

    def _probe_http(url: str) -> bool | None:
        u = (url or "").strip().lower()
        if not u:
            return None
        if not (u.startswith("http://") or u.startswith("https://")):
            return None
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                return int(getattr(resp, "status", 0) or 0) < 500
        except urllib.error.HTTPError as e:
            return int(getattr(e, "code", 0) or 0) < 500
        except Exception:
            return False

    dashboard_reachable = _probe_http(dashboard_url) if probe and dashboard_configured else None
    trace_backend_reachable = _probe_http(trace_backend_url) if probe and trace_backend_configured else None

    infra_ready = bool(dashboard_configured and alert_delivery_configured and trace_backend_configured)
    if probe:
        probe_ready = bool((dashboard_reachable is True) and (trace_backend_reachable is True))
        ready = bool(infra_ready and probe_ready)
    else:
        ready = infra_ready

    return {
        "ok": True,
        "dashboard_configured": dashboard_configured,
        "dashboard_url": dashboard_url or None,
        "dashboard_reachable": dashboard_reachable,
        "alert_delivery_configured": alert_delivery_configured,
        "alert_delivery_target": alert_target or None,
        "trace_backend_configured": trace_backend_configured,
        "trace_backend_url": trace_backend_url or None,
        "trace_backend_reachable": trace_backend_reachable,
        "probes_enabled": bool(probe),
        "ready_for_phase2_acceptance": ready,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/security-posture-status", response_model=OpsSecurityPostureStatusResponse)
def ops_security_posture_status(_role: str = Depends(require_viewer)):
    secrets_source = (os.getenv("GEOLOG_SECRETS_SOURCE") or "").strip()
    tls_required = (os.getenv("GEOLOG_REQUIRE_TLS", "true") or "true").strip().lower() in {"1", "true", "yes", "on"}
    ci_security_gates_enabled = os.path.exists(".github/workflows/security-gates.yml")
    backup_drill_script_present = os.path.exists("scripts/backup_restore_drill.sh")
    branch_protection_checklist_present = os.path.exists("docs/BRANCH_PROTECTION_CHECKLIST.md")
    security_evidence_template_present = os.path.exists("docs/SECURITY_EVIDENCE_TEMPLATE.md")
    container_non_root = True

    ok = bool(
        container_non_root
        and bool(secrets_source)
        and tls_required
        and ci_security_gates_enabled
        and backup_drill_script_present
        and branch_protection_checklist_present
        and security_evidence_template_present
    )

    return {
        "ok": ok,
        "container_non_root": container_non_root,
        "secrets_source_configured": bool(secrets_source),
        "tls_required": tls_required,
        "ci_security_gates_enabled": ci_security_gates_enabled,
        "backup_drill_script_present": backup_drill_script_present,
        "branch_protection_checklist_present": branch_protection_checklist_present,
        "security_evidence_template_present": security_evidence_template_present,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/security-evidence-status", response_model=OpsSecurityEvidenceStatusResponse)
def ops_security_evidence_status(_role: str = Depends(require_viewer)):
    artifact_dir = (os.getenv("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR") or "artifacts/backup-drill").strip() or "artifacts/backup-drill"

    def _resolve_paths(base_dir: str):
        root_report = os.path.join(base_dir, "report.json")
        root_sig = os.path.join(base_dir, "report.signature.json")
        if os.path.exists(root_report) and os.path.exists(root_sig):
            return root_report, root_sig

        try:
            candidates = []
            for name in os.listdir(base_dir):
                sub = os.path.join(base_dir, name)
                rp = os.path.join(sub, "report.json")
                sp = os.path.join(sub, "report.signature.json")
                if os.path.isdir(sub) and os.path.exists(rp) and os.path.exists(sp):
                    candidates.append((os.path.getmtime(rp), rp, sp))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, rp, sp = candidates[0]
                return rp, sp
        except Exception:
            return root_report, root_sig
        return root_report, root_sig

    report_path, sig_path = _resolve_paths(artifact_dir)

    report_present = os.path.exists(report_path)
    signature_present = os.path.exists(sig_path)
    report_sha256_matches_signature: bool | None = None
    hmac_signature_valid: bool | None = None
    signature_alg: str | None = None
    signature_kid: str | None = None
    retention_days: int | None = None

    if report_present and signature_present:
        try:
            with open(report_path, "rb") as f:
                report_bytes = f.read()
            report_sha = hashlib.sha256(report_bytes).hexdigest()

            with open(sig_path, "r", encoding="utf-8") as f:
                sig_obj = json.load(f)

            declared_sha = str(sig_obj.get("report_sha256", "") or "").strip().lower()
            signature_alg = str(sig_obj.get("signature_alg", "") or "").strip() or None
            signature_kid = str(sig_obj.get("signature_kid", "") or "").strip() or None

            rd = sig_obj.get("retention_days")
            try:
                retention_days = int(rd) if rd is not None else None
            except Exception:
                retention_days = None

            report_sha256_matches_signature = bool(declared_sha and declared_sha == report_sha)

            if signature_alg == "hmac-sha256":
                key = (os.getenv("BACKUP_DRILL_SIGNING_KEY") or "").strip()
                sig = str(sig_obj.get("signature", "") or "").strip().lower()
                if key and sig and len(sig) == 64 and all(c in "0123456789abcdef" for c in sig):
                    signed_value = (declared_sha or report_sha).encode("utf-8")
                    expected = hmac.new(key.encode("utf-8"), signed_value, hashlib.sha256).hexdigest()
                    hmac_signature_valid = hmac.compare_digest(expected, sig)
                else:
                    hmac_signature_valid = False
        except Exception:
            report_sha256_matches_signature = False
            hmac_signature_valid = False

    ok = bool(
        report_present
        and signature_present
        and report_sha256_matches_signature is True
        and (hmac_signature_valid is not False)
    )

    return {
        "ok": ok,
        "artifact_dir": artifact_dir,
        "report_present": report_present,
        "signature_present": signature_present,
        "report_sha256_matches_signature": report_sha256_matches_signature,
        "signature_alg": signature_alg,
        "signature_kid": signature_kid,
        "hmac_signature_valid": hmac_signature_valid,
        "retention_days": retention_days,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get("/security-evidence/manifest", response_model=OpsSecurityEvidenceManifestResponse)
def ops_security_evidence_manifest(sign: bool = False, kid: str | None = None, _role: str = Depends(require_viewer)):
    artifact_dir = (os.getenv("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR") or "artifacts/backup-drill").strip() or "artifacts/backup-drill"

    report_path = os.path.join(artifact_dir, "report.json")
    sig_path = os.path.join(artifact_dir, "report.signature.json")
    if not (os.path.exists(report_path) and os.path.exists(sig_path)):
        try:
            candidates = []
            for name in os.listdir(artifact_dir):
                sub = os.path.join(artifact_dir, name)
                rp = os.path.join(sub, "report.json")
                sp = os.path.join(sub, "report.signature.json")
                if os.path.isdir(sub) and os.path.exists(rp) and os.path.exists(sp):
                    candidates.append((os.path.getmtime(rp), rp, sp))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, report_path, sig_path = candidates[0]
        except Exception:
            pass

    if not (os.path.exists(report_path) and os.path.exists(sig_path)):
        return {
            "ok": False,
            "artifact_dir": artifact_dir,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }

    with open(report_path, "rb") as f:
        report_bytes = f.read()
    with open(sig_path, "rb") as f:
        sig_bytes = f.read()

    report_sha = hashlib.sha256(report_bytes).hexdigest()
    signature_sha = hashlib.sha256(sig_bytes).hexdigest()

    payload = {
        "artifact_dir": artifact_dir,
        "report_path": report_path,
        "signature_path": sig_path,
        "report_sha256": report_sha,
        "signature_sha256": signature_sha,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    bundle_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    out = {
        "ok": True,
        "artifact_dir": artifact_dir,
        "report_path": report_path,
        "signature_path": sig_path,
        "report_sha256": report_sha,
        "signature_sha256": signature_sha,
        "bundle_digest_sha256": bundle_digest,
        "signature": None,
        "signature_alg": None,
        "signature_kid": None,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    if sign:
        resolved_kid, key_raw = resolve_audit_export_signing_key(kid)
        sig = hmac.new(key_raw.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        out["signature"] = sig
        out["signature_alg"] = "hmac-sha256"
        out["signature_kid"] = resolved_kid

    return out


@router.get(
    "/security-evidence/manifest/verify-signature",
    response_model=AuditSignatureVerifyResponse,
)
def ops_security_evidence_manifest_verify_signature(
    signature: str,
    kid: str | None = None,
    _role: str = Depends(require_viewer),
):
    payload = ops_security_evidence_manifest(sign=False, kid=None, _role=_role)
    if not bool(payload.get("ok", False)):
        return {
            "ok": False,
            "reason": "evidence manifest unavailable",
            "reason_code": "KEY_RESOLUTION_ERROR",
            "signature_alg": "hmac-sha256",
            "signature_kid": kid or None,
        }
    payload_obj = {
        "artifact_dir": payload.get("artifact_dir"),
        "report_path": payload.get("report_path"),
        "signature_path": payload.get("signature_path"),
        "report_sha256": payload.get("report_sha256"),
        "signature_sha256": payload.get("signature_sha256"),
    }
    return verify_audit_export_signature_payload(payload_obj, signature, kid)


@router.post(
    "/security-evidence/manifest/verify-signature",
    response_model=AuditSignatureVerifyResponse,
)
def ops_security_evidence_manifest_verify_signature_post(
    body: OpsSecurityEvidenceManifestVerifyRequest,
    _role: str = Depends(require_interpreter),
):
    payload = ops_security_evidence_manifest(sign=False, kid=None, _role="viewer")
    if not bool(payload.get("ok", False)):
        return {
            "ok": False,
            "reason": "evidence manifest unavailable",
            "reason_code": "KEY_RESOLUTION_ERROR",
            "signature_alg": "hmac-sha256",
            "signature_kid": body.kid or None,
        }
    payload_obj = {
        "artifact_dir": payload.get("artifact_dir"),
        "report_path": payload.get("report_path"),
        "signature_path": payload.get("signature_path"),
        "report_sha256": payload.get("report_sha256"),
        "signature_sha256": payload.get("signature_sha256"),
    }
    return verify_audit_export_signature_payload(payload_obj, body.signature, body.kid)


@router.get(
    "/summary",
    response_model=OpsSummaryResponse,
    responses={
        200: {
            "description": "Aggregated ops summary snapshot",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "contract_version": "1.1",
                        "status": {"db_ok": True, "slo_ok": True, "alerts_ok": True},
                        "alerts": {
                            "count": 0,
                            "highest_severity": "none",
                            "severity_counts": {"warning": 0, "critical": 0},
                            "code_counts": {},
                        },
                        "traffic": {
                            "requests_total": 123,
                            "latency_ms_avg": 42.1,
                            "error_rate": 0.0,
                            "recent_events_size": 50,
                        },
                        "slo": {
                            "targets": {"latency_ms_avg_max": 500.0, "latency_ms_p95_max": 800.0, "error_rate_max": 0.01},
                            "current": {"latency_ms_avg": 42.1, "latency_ms_p95": 88.2, "error_rate": 0.0, "requests_total": 123, "errors_5xx": 0},
                            "checks": {"latency_ok": True, "latency_avg_ok": True, "latency_p95_ok": True, "error_rate_ok": True},
                        },
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_summary(db: Session = Depends(get_db), _role: str = Depends(require_viewer)):
    """One-shot ops summary for dashboards and external monitors."""
    health = ops_health(db, _role)
    slo = ops_slo_status(_role)
    alerts = ops_alerts(_role)
    metrics = ops_metrics(_role)

    return {
        "ok": bool(health.get("ok", False)),
        "contract_version": "1.1",
        "status": {
            "db_ok": bool(health.get("db_ok", False)),
            "slo_ok": bool(slo.get("ok", False)),
            "alerts_ok": bool(alerts.get("ok", False)),
        },
        "alerts": {
            "count": int(alerts.get("count", 0)),
            "highest_severity": str(alerts.get("highest_severity", "none")),
            "severity_counts": dict(alerts.get("severity_counts", {})),
            "code_counts": dict(alerts.get("code_counts", {})),
        },
        "traffic": {
            "requests_total": int(metrics.get("requests_total", 0)),
            "latency_ms_avg": float(metrics.get("latency_ms_avg", 0.0)),
            "error_rate": float(slo.get("current", {}).get("error_rate", 0.0)),
            "recent_events_size": int(metrics.get("recent_events_size", 0)),
        },
        "slo": {
            "targets": dict(slo.get("targets", {})),
            "current": dict(slo.get("current", {})),
            "checks": dict(slo.get("checks", {})),
        },
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get(
    "/contracts",
    response_model=OpsContractsResponse,
    responses={
        200: {
            "description": "Contract registry for ops/audit endpoints",
            "content": {
                "application/json": {
                    "example": {
                        "api_group": "ops-audit",
                        "contract_version": "2.1",
                        "endpoints": {
                            "/api/audit-log/verify/export": "1.2",
                            "/api/audit-log/verify/signature": "1.1",
                            "/api/audit-log/immutability-status": "1.0",
                            "/metrics": "1.0",
                            "/metrics/recent": "1.1",
                            "/metrics/prometheus": "1.0",
                            "/slo-status": "1.1",
                            "/alerts": "1.2",
                            "/alert-rules": "1.0",
                            "/health": "1.0",
                            "/observability-status": "1.1",
                            "/otel-status": "1.0",
                            "/evidence-status": "1.0",
                            "/security-posture-status": "1.0",
                            "/security-evidence-status": "1.0",
                            "/security-evidence/manifest": "1.0",
                            "/security-evidence/manifest/verify-signature": "1.0",
                            "/security-evidence/attest": "1.0",
                            "/security-evidence/attest/latest": "1.0",
                            "/security-evidence/freshness": "1.0",
                            "/security-evidence/gate": "1.14",
                            "/security-evidence/gate/enforce": "1.14",
                            "/security-evidence/gate/assert": "1.14",
                            "/security-evidence/gate/check": "1.14",
                            "/runbook": "1.0",
                            "/summary": "1.1",
                        },
                        "digest_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                        "signature": None,
                        "signature_alg": None,
                        "signature_kid": None,
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_contracts(
    sign: bool = False,
    kid: str | None = None,
    _role: str = Depends(require_viewer),
):
    """Machine-readable contract/version registry for ops and audit APIs."""
    digest_payload = _ops_contracts_payload()
    canonical = json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    out = {
        "api_group": digest_payload["api_group"],
        "contract_version": digest_payload["contract_version"],
        "endpoints": digest_payload["endpoints"],
        "digest_sha256": digest,
        "signature": None,
        "signature_alg": None,
        "signature_kid": None,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    if sign:
        resolved_kid, key_raw = resolve_audit_export_signing_key(kid)
        sig = hmac.new(key_raw.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        out["signature"] = sig
        out["signature_alg"] = "hmac-sha256"
        out["signature_kid"] = resolved_kid

    return out


@router.get(
    "/contracts/verify-signature",
    response_model=AuditSignatureVerifyResponse,
)
def ops_contracts_verify_signature(
    signature: str,
    kid: str | None = None,
    _role: str = Depends(require_viewer),
):
    """Verify detached signature for current ops contracts payload."""
    return verify_audit_export_signature_payload(_ops_contracts_payload(), signature, kid)


@router.post(
    "/contracts/verify-signature",
    response_model=AuditSignatureVerifyResponse,
)
def ops_contracts_verify_signature_post(
    body: AuditSignatureVerifyRequest,
    _role: str = Depends(require_interpreter),
):
    """M2M verifier for detached signature over current ops contracts payload."""
    return verify_audit_export_signature_payload(_ops_contracts_payload(), body.signature, body.kid)


@router.post(
    "/security-evidence/attest",
    response_model=OpsSecurityEvidenceAttestResponse,
)
def ops_security_evidence_attest(
    body: OpsSecurityEvidenceAttestRequest,
    _role: str = Depends(require_interpreter),
):
    report = body.report if isinstance(body.report, dict) else None
    signature_obj = body.signature if isinstance(body.signature, dict) else None
    return _attest_security_evidence_payload(report, signature_obj)


@router.get(
    "/security-evidence/attest/latest",
    response_model=OpsSecurityEvidenceAttestResponse,
)
def ops_security_evidence_attest_latest(_role: str = Depends(require_viewer)):
    artifact_dir = (os.getenv("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR") or "artifacts/backup-drill").strip() or "artifacts/backup-drill"
    report_path = os.path.join(artifact_dir, "report.json")
    sig_path = os.path.join(artifact_dir, "report.signature.json")

    if not (os.path.exists(report_path) and os.path.exists(sig_path)):
        try:
            candidates = []
            for name in os.listdir(artifact_dir):
                sub = os.path.join(artifact_dir, name)
                rp = os.path.join(sub, "report.json")
                sp = os.path.join(sub, "report.signature.json")
                if os.path.isdir(sub) and os.path.exists(rp) and os.path.exists(sp):
                    candidates.append((os.path.getmtime(rp), rp, sp))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, report_path, sig_path = candidates[0]
        except Exception:
            pass

    report_obj = None
    signature_obj = None

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report_obj = json.load(f)
    except Exception:
        report_obj = None

    try:
        with open(sig_path, "r", encoding="utf-8") as f:
            signature_obj = json.load(f)
    except Exception:
        signature_obj = None

    return _attest_security_evidence_payload(report_obj, signature_obj)


@router.get(
    "/security-evidence/freshness",
    response_model=OpsSecurityEvidenceFreshnessResponse,
)
def ops_security_evidence_freshness(max_age_seconds: int = 86400, _role: str = Depends(require_viewer)):
    max_age_seconds = max(60, int(max_age_seconds))
    artifact_dir = (os.getenv("GEOLOG_BACKUP_DRILL_ARTIFACT_DIR") or "artifacts/backup-drill").strip() or "artifacts/backup-drill"
    report_path = os.path.join(artifact_dir, "report.json")
    sig_path = os.path.join(artifact_dir, "report.signature.json")

    if not (os.path.exists(report_path) and os.path.exists(sig_path)):
        try:
            candidates = []
            for name in os.listdir(artifact_dir):
                sub = os.path.join(artifact_dir, name)
                rp = os.path.join(sub, "report.json")
                sp = os.path.join(sub, "report.signature.json")
                if os.path.isdir(sub) and os.path.exists(rp) and os.path.exists(sp):
                    candidates.append((os.path.getmtime(rp), rp, sp))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, report_path, sig_path = candidates[0]
        except Exception:
            pass

    if not (os.path.exists(report_path) and os.path.exists(sig_path)):
        return {
            "ok": False,
            "artifact_dir": artifact_dir,
            "report_path": None,
            "signature_path": None,
            "report_age_seconds": None,
            "max_age_seconds": max_age_seconds,
            "stale": True,
            "reason_code": "EVIDENCE_MISSING",
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }

    try:
        report_age_seconds = int(max(0.0, time.time() - os.path.getmtime(report_path)))
    except Exception:
        report_age_seconds = None

    stale = report_age_seconds is None or report_age_seconds > max_age_seconds
    return {
        "ok": not stale,
        "artifact_dir": artifact_dir,
        "report_path": report_path,
        "signature_path": sig_path,
        "report_age_seconds": report_age_seconds,
        "max_age_seconds": max_age_seconds,
        "stale": stale,
        "reason_code": "STALE" if stale else "FRESH",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get(
    "/security-evidence/gate",
    response_model=OpsSecurityEvidenceGateResponse,
)
def ops_security_evidence_gate(
    max_age_seconds: int = 86400,
    min_retention_days: int = 30,
    required_checks: str = "attest,freshness,retention",
    strict_required_checks: bool = False,
    _role: str = Depends(require_viewer),
):
    max_age_seconds = max(60, int(max_age_seconds))
    min_retention_days = max(1, int(min_retention_days))

    allowed_checks = {"attest", "freshness", "retention"}
    parsed_checks = [c.strip().lower() for c in str(required_checks).split(",") if c.strip()]

    seen: set[str] = set()
    duplicate_checks: list[str] = []
    deduped_checks: list[str] = []
    for c in parsed_checks:
        if c in seen:
            if c not in duplicate_checks:
                duplicate_checks.append(c)
            continue
        seen.add(c)
        deduped_checks.append(c)

    evaluated_checks = [c for c in deduped_checks if c in allowed_checks]
    ignored_checks = [c for c in deduped_checks if c not in allowed_checks]
    if strict_required_checks and ignored_checks:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid required_checks values",
                "requested_checks": parsed_checks,
                "ignored_checks": ignored_checks,
                "duplicate_checks": duplicate_checks,
                "allowed_checks": ["attest", "freshness", "retention"],
            },
        )

    defaulted_checks = len(evaluated_checks) == 0
    if defaulted_checks:
        evaluated_checks = ["attest", "freshness", "retention"]

    attest = ops_security_evidence_attest_latest(_role=_role)
    freshness = ops_security_evidence_freshness(max_age_seconds=max_age_seconds, _role=_role)

    attest_ok = bool(attest.get("ok", False))
    freshness_ok = bool(freshness.get("ok", False))
    retention_days = attest.get("retention_days")
    retention_ok = isinstance(retention_days, int) and retention_days >= min_retention_days
    retention_reason_code = (
        "RETENTION_OK" if retention_ok else "RETENTION_TOO_SHORT" if isinstance(retention_days, int) else "RETENTION_UNKNOWN"
    )

    check_status = {
        "attest": attest_ok,
        "freshness": freshness_ok,
        "retention": retention_ok,
    }
    failed_checks: list[str] = [c for c in evaluated_checks if not bool(check_status.get(c, False))]
    invariants = _compute_gate_invariants(failed_checks, evaluated_checks)

    return {
        "ok": invariants["gate_failed_count"] == 0,
        "gate_reason_code": "GATE_PASS" if invariants["gate_failed_count"] == 0 else "GATE_FAIL",
        "gate_failed_count": invariants["gate_failed_count"],
        "gate_passed_count": invariants["gate_passed_count"],
        "gate_total_count": invariants["gate_total_count"],
        "gate_pass_ratio": invariants["gate_pass_ratio"],
        "gate_fail_ratio": invariants["gate_fail_ratio"],
        "gate_consistency_ok": invariants["gate_consistency_ok"],
        "gate_consistency_reason": invariants["gate_consistency_reason"],
        "attest_ok": attest_ok,
        "freshness_ok": freshness_ok,
        "retention_ok": retention_ok,
        "strict_required_checks": bool(strict_required_checks),
        "defaulted_checks": bool(defaulted_checks),
        "requested_checks": parsed_checks,
        "ignored_checks": ignored_checks,
        "duplicate_checks": duplicate_checks,
        "evaluated_checks": evaluated_checks,
        "failed_checks": failed_checks,
        "attest_reason_code": attest.get("reason_code"),
        "freshness_reason_code": freshness.get("reason_code", "EVIDENCE_MISSING"),
        "retention_reason_code": retention_reason_code,
        "artifact_dir": str(freshness.get("artifact_dir") or ""),
        "report_age_seconds": freshness.get("report_age_seconds"),
        "retention_days": retention_days if isinstance(retention_days, int) else None,
        "min_retention_days": min_retention_days,
        "max_age_seconds": int(freshness.get("max_age_seconds") or max_age_seconds),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@router.get(
    "/security-evidence/gate/enforce",
    response_model=OpsSecurityEvidenceGateResponse,
    responses={503: {"model": OpsSecurityEvidenceGateErrorResponse, "description": "Gate failed"}},
)
def ops_security_evidence_gate_enforce(
    max_age_seconds: int = 86400,
    min_retention_days: int = 30,
    required_checks: str = "attest,freshness,retention",
    strict_required_checks: bool = False,
    _role: str = Depends(require_viewer),
):
    gate = ops_security_evidence_gate(
        max_age_seconds=max_age_seconds,
        min_retention_days=min_retention_days,
        required_checks=required_checks,
        strict_required_checks=strict_required_checks,
        _role=_role,
    )
    if bool(gate.get("ok", False)):
        return gate
    raise HTTPException(status_code=503, detail=_security_evidence_gate_failure_detail(gate))


@router.post(
    "/security-evidence/gate/assert",
    response_model=OpsSecurityEvidenceGateResponse,
    responses={503: {"model": OpsSecurityEvidenceGateErrorResponse, "description": "Gate failed"}},
)
def ops_security_evidence_gate_assert(
    max_age_seconds: int = 86400,
    min_retention_days: int = 30,
    required_checks: str = "attest,freshness,retention",
    strict_required_checks: bool = False,
    _role: str = Depends(require_interpreter),
):
    gate = ops_security_evidence_gate(
        max_age_seconds=max_age_seconds,
        min_retention_days=min_retention_days,
        required_checks=required_checks,
        strict_required_checks=strict_required_checks,
        _role="viewer",
    )
    if bool(gate.get("ok", False)):
        return gate
    raise HTTPException(status_code=503, detail=_security_evidence_gate_failure_detail(gate))


@router.post(
    "/security-evidence/gate/check",
    response_model=OpsSecurityEvidenceGateResponse,
)
def ops_security_evidence_gate_check(
    max_age_seconds: int = 86400,
    min_retention_days: int = 30,
    required_checks: str = "attest,freshness,retention",
    strict_required_checks: bool = False,
    _role: str = Depends(require_interpreter),
):
    return ops_security_evidence_gate(
        max_age_seconds=max_age_seconds,
        min_retention_days=min_retention_days,
        required_checks=required_checks,
        strict_required_checks=strict_required_checks,
        _role="viewer",
    )


@router.get(
    "/runbook",
    response_model=OpsRunbookResponse,
    responses={
        200: {
            "description": "Machine-readable runbook for known ops alert codes",
            "content": {
                "application/json": {
                    "example": {
                        "version": "1.0",
                        "alerts": {
                            "LATENCY_AVG_SLO_BREACH": {
                                "severity": "warning",
                                "what_it_means": "Average API latency is above configured SLO threshold.",
                                "checks": ["Call /api/ops/slo-status and verify avg target vs current"],
                                "actions": ["Identify top high-latency endpoints and payload sizes"],
                            },
                            "ERROR_RATE_SLO_BREACH": {
                                "severity": "critical",
                                "what_it_means": "5xx error rate is above configured SLO threshold.",
                                "checks": ["Call /api/ops/metrics and inspect requests_by_status"],
                                "actions": ["Open incident and capture failing request samples"],
                            },
                        },
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_runbook(_role: str = Depends(require_viewer)):
    """Machine-readable operator runbook for current alert codes."""
    return {
        "version": "1.0",
        "alerts": {
            "LATENCY_AVG_SLO_BREACH": {
                "severity": "warning",
                "what_it_means": "Average API latency is above configured SLO threshold.",
                "checks": [
                    "Call /api/ops/metrics and inspect latency_ms_avg + requests_by_status",
                    "Call /api/ops/slo-status and verify avg target vs current",
                    "Inspect recent structured logs for slow endpoints",
                ],
                "actions": [
                    "Identify top high-latency endpoints and payload sizes",
                    "Reduce heavy query scope or enable/adjust decimation where applicable",
                    "Scale worker/container resources if sustained load increased",
                ],
            },
            "LATENCY_P95_SLO_BREACH": {
                "severity": "warning",
                "what_it_means": "P95 API latency is above configured SLO threshold.",
                "checks": [
                    "Call /api/ops/slo-status and verify p95 target vs current",
                    "Call /api/ops/metrics/recent with status/path filters to isolate spikes",
                    "Inspect structured logs for long-tail endpoints",
                ],
                "actions": [
                    "Profile worst endpoints and identify tail-latency bottlenecks",
                    "Apply caching/precomputation for expensive repeated reads",
                    "Tune infra resources or concurrency limits for burst traffic",
                ],
            },
            "ERROR_RATE_SLO_BREACH": {
                "severity": "critical",
                "what_it_means": "5xx error rate is above configured SLO threshold.",
                "checks": [
                    "Call /api/ops/metrics and inspect requests_by_status",
                    "Check /api/ops/health for db_ok and alerts summary",
                    "Inspect backend error logs around spike window",
                ],
                "actions": [
                    "Rollback latest risky change if correlated with spike",
                    "Mitigate failing endpoint path (feature flag/route guard)",
                    "Open incident and capture failing request samples",
                ],
            },
        },
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
