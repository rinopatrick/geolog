"""Optional OpenTelemetry tracing.

The application runs without any OpenTelemetry package installed. When
`GEOLOG_OTEL_ENABLED=true` and the optional dependencies are present, FastAPI
requests are instrumented and exported over OTLP/HTTP. Missing packages are a
warning, not a startup failure.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

try:
    from version import __version__
except ImportError:
    from backend.version import __version__

logger = logging.getLogger("geolog.tracing")

_PROVIDER: Any = None
_INSTRUMENTED = False


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _environment() -> str:
    return (os.getenv("GEOLOG_ENV") or os.getenv("ENV") or "dev").strip().lower()


def config() -> dict[str, Any]:
    return {
        "enabled": _truthy(os.getenv("GEOLOG_OTEL_ENABLED")),
        "endpoint": (os.getenv("GEOLOG_OTEL_ENDPOINT") or "http://localhost:4318/v1/traces").strip(),
        "service_name": (os.getenv("GEOLOG_OTEL_SERVICE_NAME") or "geolog").strip(),
        "sample_ratio": os.getenv("GEOLOG_OTEL_SAMPLE_RATIO", "1.0"),
        "headers": os.getenv("GEOLOG_OTEL_HEADERS", ""),
        "excluded_urls": (
            os.getenv("GEOLOG_OTEL_EXCLUDED_URLS")
            or "api/health,api/ops/metrics,api/ops/metrics/prometheus"
        ).strip(),
    }


def _ratio(raw: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0
    return min(1.0, max(0.0, value))


def _headers(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("GEOLOG_OTEL_HEADERS is not valid JSON; ignoring it")
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


def setup_tracing(app: Any) -> bool:
    """Instrument the FastAPI app when enabled and the SDK is installed."""
    global _PROVIDER, _INSTRUMENTED

    cfg = config()
    if not cfg["enabled"]:
        return False
    if _INSTRUMENTED:
        return True

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError as exc:
        logger.warning(
            "OpenTelemetry is enabled but not installed (%s); tracing disabled. "
            "Install the packages from docs/PRODUCTION_HARDENING.md.",
            exc,
        )
        return False

    resource = Resource.create(
        {
            "service.name": cfg["service_name"],
            "service.version": __version__,
            "deployment.environment": _environment(),
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(_ratio(cfg["sample_ratio"])),
    )
    exporter = OTLPSpanExporter(
        endpoint=cfg["endpoint"],
        headers=_headers(cfg["headers"]),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=cfg["excluded_urls"] or None,
    )
    _PROVIDER = provider
    _INSTRUMENTED = True
    logger.info(
        "OpenTelemetry tracing enabled (service=%s endpoint=%s)",
        cfg["service_name"],
        cfg["endpoint"],
    )
    return True


def shutdown_tracing() -> None:
    global _PROVIDER, _INSTRUMENTED
    if _PROVIDER is not None:
        try:
            _PROVIDER.shutdown()
        except Exception:
            logger.debug("OpenTelemetry provider shutdown failed", exc_info=True)
    _PROVIDER = None
    _INSTRUMENTED = False
