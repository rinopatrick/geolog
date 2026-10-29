"""Optional OpenTelemetry tracing stays a no-op unless configured."""

from __future__ import annotations

import sys

from backend import tracing


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GEOLOG_OTEL_ENABLED", raising=False)
    assert tracing.setup_tracing(object()) is False


def test_missing_sdk_is_a_warning_not_a_failure(monkeypatch):
    monkeypatch.setenv("GEOLOG_OTEL_ENABLED", "true")
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    assert tracing.setup_tracing(object()) is False


def test_config_defaults(monkeypatch):
    monkeypatch.setenv("GEOLOG_OTEL_ENABLED", "true")
    monkeypatch.setenv("GEOLOG_OTEL_SAMPLE_RATIO", "0.25")
    cfg = tracing.config()
    assert cfg["enabled"] is True
    assert cfg["service_name"] == "geolog"
    assert cfg["endpoint"].endswith("/v1/traces")
    assert cfg["sample_ratio"] == "0.25"
    assert "api/health" in cfg["excluded_urls"]


def test_header_and_ratio_helpers():
    assert tracing._ratio("2") == 1.0
    assert tracing._ratio("-1") == 0.0
    assert tracing._ratio("nope") == 1.0
    assert tracing._headers('{"Authorization": "Bearer x"}') == {"Authorization": "Bearer x"}
    assert tracing._headers("not json") == {}
